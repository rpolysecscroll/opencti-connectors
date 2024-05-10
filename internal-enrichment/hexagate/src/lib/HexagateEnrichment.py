import os
from typing import Dict
from pycti import OpenCTIConnectorHelper
from stix2 import Note, TLP_WHITE, Identity
import requests
import json


class HexagateEnrichmentConnector:
    """
    Attributes:
        helper (OpenCTIConnectorHelper): The helper to use.
        update_existing_data (str): Whether to update existing data or not in OpenCTI.
        author_id (str): the identity attributed to creation of the Note
        api_key (str): the api key for authenticating to the hexagate api
    """
    def __init__(self):
        self.helper = OpenCTIConnectorHelper({})
        self.api_key = os.environ.get("HEXAGATE_API_KEY")
        self.author_id = os.environ.get("HEXAGATE_AUTHOR_ID")

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
            return self.hexagate_enrich_addr(observable)
        else:
            # this should never happen
            self.helper.log_error("wrong type process data: " + str(data))

    def hexagate_enrich_addr(self, observable):
        """Create the Note based on Hexagate results

        Build a bundle

        Args:
            observable (stix2.Observable): attribute contains the cryptocurrency wallet to enrich.
        """
        # get the cryptocurrency address
        addr = observable["value"]
        self.helper.log_info(f"Retreiving data on {addr}")

        # the url specific to performing address lookups on ethereum mainnet
        url = "https://api.hexagate.com/api/v1/ethereum/mainnet/address/analyze"

        # the payload hexagate api expects in the post request
        payload = json.dumps({
            "address": addr
        })

        # requires a valid hexagate api key
        headers = {
            'Content-Type': 'application/json',
            'X-Hexagate-Api-Key': self.api_key
        }

        # retrieve enrichment on an address from Hexagate
        response = requests.request("POST", url, headers=headers, data=payload)

        # parse the result of the Hexagate enrichment query
        abstract = 'Name: {}, Risk: {}, Type: {}'.format(response.json()['name'],response.json()['risk_level'],response.json()['type'])
        details = ''
        for issue in response.json()['security_issues']:
            if not issue['risk_level'] == 'LOW':
                details = '{}\n\nRisk: {}'.format(issue['type'],issue['risk_level'])
                d_list = ''
                for d in issue['extra_details']:
                    d_list = d_list + ' ' + d
                details = details + '\n\n' + d_list

        # if the address doesn't trigger any security issues add a defult None value
        if details == "":
            details = "None"

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

        # Send the bundle of stix objects, here the hexagate enrichment info, to OpenCTI
        bundle = self.helper.stix2_create_bundle(stix_objects)
        bundles_sent = self.helper.send_stix2_bundle(bundle)
        self.helper.log_info(f"Sent {len(bundles_sent)} stix bundle(s) for worker import")

        return None

    # Start the main loop
    def start(self):
        self.helper.listen(message_callback=self.process_message)
