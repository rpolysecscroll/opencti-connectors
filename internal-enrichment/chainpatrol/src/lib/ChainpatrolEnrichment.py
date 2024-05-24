import os
from typing import Dict
from pycti import OpenCTIConnectorHelper
from stix2 import Note, TLP_WHITE, Identity
import requests
import json

class ChainpatrolEnrichmentConnector:
    """
    Attributes:
        helper (OpenCTIConnectorHelper): The helper to use.
        update_existing_data (str): Whether to update existing data or not in OpenCTI.
        author_id (str): the identity attributed to creation of the Note
        api_key (str): the api key for authenticating to the hexagate api
    """
    def __init__(self):
        self.helper = OpenCTIConnectorHelper({})
        self.api_key = os.environ.get("CHAINPATROL_API_KEY")
        self.author_id = os.environ.get("CHAINPATROL_AUTHOR_ID")

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

        # we only care about domain names, ignore any other entity type
        if observable["entity_type"] == "Domain-Name":
            return self.chainpatrol_enrich_domain(observable)
        else:
            # this should never happen
            self.helper.log_error("wrong type process data: " + str(data))

    def chainpatrol_enrich_domain(self, observable):
        """Create the Note based on Chainpatrol results

        Build a bundle

        Args:
            observable (stix2.Observable): attribute contains the domain name to enrich.
        """
        domain = observable["value"]
        self.helper.log_info(f"Retreiving data on {domain}")
        url = "https://app.chainpatrol.io/api/v2/asset/details"

        payload = {"content": domain}
        headers = {"Content-Type": "application/json", 'X-API-KEY': self.api_key}

        response = requests.request("POST", url, json=payload, headers=headers)

        details = ''
        abstract = ''

        if response.json()['status'] == 'BLOCKED':
            abstract ='Result: {}'.format(response.json()['status'])
            details = '({}) -  Chainpatrol Report: {}'.format(response.json()['reason'],response.json()['reportUrl'])
        if response.json()['status'] == 'ALLOWED':
            abstract ='Result: {}'.format(response.json()['status'])
            details = 'Chainpatrol Report: {}'.format(response.json()['reportUrl'])
        else:
            abstract ='Result: {}'.format(response.json()['status'])
            details = '({})'.format(response.json()['reason'])

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
