import os
from typing import Dict
from pycti import OpenCTIConnectorHelper
from stix2 import Note, TLP_WHITE, Identity
import requests
import json
from ens import ENS
from web3 import Web3
from etherscan import Etherscan

class EtherscanEnrichmentConnector:
    """
    Attributes:
        helper (OpenCTIConnectorHelper): The helper to use.
        update_existing_data (str): Whether to update existing data or not in OpenCTI.
        author_id (str): the identity attributed to creation of the Note
        api_key (str): the api key for authenticating to the hexagate api
    """
    def __init__(self):
        self.helper = OpenCTIConnectorHelper({})
        self.api_key = os.environ.get("ETHERSCAN_API_KEY")
        self.author_id = os.environ.get("ETHERSCAN_AUTHOR_ID")
        self.alchemy_url = os.environ.get("ALCHEMY_URL")

        self.eth = Etherscan(self.api_key)
        self.w3 = Web3(Web3.HTTPProvider(self.alchemy_url))
        self.ns = ENS.from_web3(self.w3)

        update_existing_data = os.environ.get("CONNECTOR_UPDATE_EXISTING_DATA", "false")
        if update_existing_data.lower() in ["true", "false"]:
            self.update_existing_data = update_existing_data.lower()
        else:
            msg = f"Error when grabbing CONNECTOR_UPDATE_EXISTING_DATA environment variable: '{self.interval}'. It SHOULD be either `true` or `false`. `false` is assumed. "
            self.helper.log_warning(msg)
            self.update_existing_data = "false"

    def process_message(self, data: Dict):
        """Processing the enrichment request

        Build a bundl

        Args:
            data (dict): The data to process. The `enrichment_entity` attribute contains the object to enrich.
        """
        self.entity_id = data["entity_id"]
        observable = self.helper.api.stix_cyber_observable.read(id=self.entity_id)

        # we only care about cryptocurrency addresses, ignore any other entity type
        if observable["entity_type"] == "Cryptocurrency-Wallet":
            return self.etherscan_enrich_addr(observable)
        else:
            # this should never happen
            self.helper.log_error("wrong type process data: " + str(data))

    def etherscan_enrich_addr(self, observable):
        """Create the Note based on Etherscan results

        Build a bundle

        Args:
            observable (stix2.Observable): attribute contains the cryptocurrency wallet to enrich.
        """
        # get the cryptocurrency address
        addr = observable["value"]
        self.helper.log_info(f"Retreiving data on {addr}")
        address = Web3.to_checksum_address(addr)

        code = self.w3.eth.get_code(address)

        isContract = False
        if len(code) > 0:
            isContract = True

        domain = self.ns.name(address)
        owner = "None"
        if not domain == None:
            owner = self.ns.owner(domain)

        abstract ='Name: {}'.format(domain)
        details = 'Name: {}, Contract: {}, Owner: {}'.format(domain,isContract,owner)

        # start creating a list of stix objects
        stix_objects = []

        # create a "Note" object containing the enrichment results
        note = Note(
            type="note",
            abstract=abstract,
            content=details,
            created_by_ref=self.author_id,
            object_refs=[self.entity_id],
            object_marking_refs=TLP_WHITE,
        )
        stix_objects.append(note)

        # Send the bundle of stix objects, the etherscan enrichment info, to OpenCTI
        bundle = self.helper.stix2_create_bundle(stix_objects)
        bundles_sent = self.helper.send_stix2_bundle(bundle)
        self.helper.log_info(f"Sent {len(bundles_sent)} stix bundle(s) for worker import")

        return None

    # Start the main loop
    def start(self):
        self.helper.listen(message_callback=self.process_message)
