from lib.HexagateEnrichment import HexagateEnrichmentConnector

class CustomConnector(HexagateEnrichmentConnector):
    def __init__(self):
        super().__init__()

    def _process_message(self, data):
        # This method isn't being used, instead we use process_message from the HexagateEnrichmentConnector
        raise NotImplementedError("This method has not been implemented yet.")

if __name__ == "__main__":
    connector = CustomConnector()
    connector.start()
