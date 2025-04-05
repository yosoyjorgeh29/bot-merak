from datetime import datetime

# Global variables
websocket_is_connected = False
# try fix ssl.SSLEOFError: EOF occurred in violation of protocol (_ssl.c:2361)
ssl_Mutual_exclusion = False  # mutex read write
# if false websocket can sent self.websocket.send(data)
# else can not sent self.websocket.send(data)
ssl_Mutual_exclusion_write = False  # if thread write

SSID = None
DEMO = None

check_websocket_if_error = False
websocket_error_reason = None

balance_id = None
balance = None
balance_type = None
balance_updated = None
result = None
order_data = {}
order_open = []
order_closed = []
closed_deals = []
stat = []
pairs = {}

loglevel = 'INFO'

# To get the payment details for the different pairs
PayoutData = None

def logger(message, lvl):
    if loglevel == lvl:
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        print('%s :: %s' %(str(dt), str(message)))
    return
