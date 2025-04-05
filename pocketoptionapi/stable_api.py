import asyncio, threading, sys, json, time, operator
from datetime import datetime
from tzlocal import get_localzone
from pocketoptionapi.api import PocketOptionAPI
import pocketoptionapi.constants as OP_code
import pocketoptionapi.global_value as global_value
from collections import defaultdict
from collections import deque
import pandas as pd

local_zone_name = get_localzone()

# logger = logging.getLogger(__name__)

def get_balance():
    return global_value.balance

class PocketOption:
    __version__ = "1.0.0"

    def __init__(self, ssid, demo):
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                     3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]
        global_value.SSID = ssid
        global_value.DEMO = demo
        # print(f"Modo Demo: {demo}")
        global_value.logger("Modo Demo: %s" % str(demo), "INFO")
        self.suspend = 0.5
        self.thread = None
        self.subscribe_candle = []
        self.subscribe_candle_all_size = []
        self.subscribe_mood = []
        self.get_realtime_strike_list_temp_data = {}
        self.get_realtime_strike_list_temp_expiration = 0
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          r"Chrome/66.0.3359.139 Safari/537.36"}
        self.SESSION_COOKIE = {}
        self.api = PocketOptionAPI()
        self.loop = asyncio.get_event_loop()

    def get_server_timestamp(self):
        return self.api.time_sync.server_timestamp
        
    def Stop(self):
        sys.exit()

    def get_server_datetime(self):
        return self.api.time_sync.server_datetime

    def set_session(self, header, cookie):
        self.SESSION_HEADER = header
        self.SESSION_COOKIE = cookie

    def get_async_order(self, buy_order_id):
        if self.api.order_async["deals"][0]["id"] == buy_order_id:
            return self.api.order_async["deals"][0]
        else:
            return None

    def get_async_order_id(self, buy_order_id):
        return self.api.order_async["deals"][0][buy_order_id]

    def start_async(self):
        asyncio.run(self.api.connect())
        
    def disconnect(self):
        try:
            if global_value.websocket_is_connected:
                asyncio.run(self.api.close())
                global_value.websocket_is_connected = False
                # logger.debug("WebSocket connection closed successfully.")
                global_value.logger("WebSocket connection closed successfully.", "DEBUG")
            else:
                # logger.debug("WebSocket was not connected.")
                global_value.logger("WebSocket was not connected.", "DEBUG")

            if self.loop is not None:
                for task in asyncio.all_tasks(self.loop):
                    task.cancel()

                if not self.loop.is_closed():
                    self.loop.stop()
                    self.loop.close()
                    # logger.debug("Event loop stopped and closed successfully.")
                    global_value.logger("Event loop stopped and closed successfully.", "DEBUG")

            if self.api.websocket_thread is not None and self.api.websocket_thread.is_alive():
                self.api.websocket_thread.join()
                # logger.debug("WebSocket thread closed successfully.")
                global_value.logger("WebSocket thread closed successfully.", "DEBUG")

        except Exception as e:
            # logging.error(f"Error during disconnection: {e}")
            global_value.logger("Error during disconnection: %s" % str(e), "ERROR")

    def connect(self):
        try:
            websocket_thread = threading.Thread(target=self.api.connect, daemon=True)
            websocket_thread.start()

        except Exception as e:
            # logging.error(f"Error connecting: {e}")
            global_value.logger("Error connecting: %s" % str(e), "ERROR")
            return False
        return True
    
    def GetPayout(self, pair):
        try:
            data = self.api.GetPayoutData()
            data = json.loads(data)
            data2 = None
            for i in data:
                if i[1] == pair:
                    data2 = i
            return data2[5]
        except:
            return None

    @staticmethod
    def check_connect():
        if global_value.websocket_is_connected == 0:
            return False
        elif global_value.websocket_is_connected is None:
            return False
        else:
            return True

    @staticmethod
    def get_balance():
        if global_value.balance_updated:
            return global_value.balance
        else:
            return None
            
    @staticmethod
    def check_open():
        return global_value.order_open
        
    @staticmethod
    def check_order_closed(ido):
        while ido not in global_value.order_closed:
            time.sleep(0.1)

        for pack in global_value.stat:
            if pack[0] == ido:
               # logger.debug('Closed Order',pack[1])
               global_value.logger("Closed Order %s" % str(pack[1]), "DEBUG")

        return pack[0]
    
    def buy(self, amount, active, action, expirations):
        self.api.buy_multi_option = {}
        self.api.buy_successful = None
        req_id = "buy"

        try:
            if req_id not in self.api.buy_multi_option:
                self.api.buy_multi_option[req_id] = {"id": None}
            else:
                self.api.buy_multi_option[req_id]["id"] = None
        except Exception as e:
            # logger.error(f"Error initializing buy_multi_option: {e}")
            global_value.logger("Error initializing buy_multi_option: %s" % str(e), "ERROR")
            return False, None

        global_value.order_data = None
        global_value.result = None

        #print(amount, active, action, expirations, req_id)
        self.api.buyv3(amount, active, action, expirations, req_id)

        start_t = time.time()
        while True:
            if global_value.result is not None and global_value.order_data is not None:
                break
            if time.time() - start_t >= 5:
                if isinstance(global_value.order_data, dict) and "error" in global_value.order_data:
                    # logger.error(global_value.order_data["error"])
                    global_value.logger(str(global_value.order_data["error"]), "ERROR")
                else:
                    # logger.error("Unknown error occurred during purchase operation")
                    global_value.logger("Unknown error occurred during purchase operation", "ERROR")
                return False, None
            time.sleep(0.1)

        return global_value.result, global_value.order_data.get("id", None)

    def check_win(self, id_number):
        start_t = time.time()
        order_info = None

        while True:
            try:
                order_info = self.get_async_order(id_number)
                if order_info and "id" in order_info and order_info["id"] is not None:
                    break
            except:
                pass

            if time.time() - start_t >= 180:
                # logger.error("Timeout: Unable to retrieve order information in time.")
                global_value.logger("Timeout: Unable to retrieve order information in time.", "ERROR")
                return None, "unknown"

            time.sleep(0.1)

        if order_info and "profit" in order_info:
            status = "win" if order_info["profit"] > 0 else "loose"
            return order_info["profit"], status
        else:
            # logger.error("Invalid order information retrieved.")
            global_value.logger("Invalid order information retrieved.", "ERROR")
            return None, "unknown"

    @staticmethod
    def last_time(timestamp, period):
        timestamp_arredondado = (timestamp // period) * period
        return int(timestamp_arredondado)

    def get_payout(self):
        return self.api.GetPayoutData()

    def get_deals(self):
        return self.api.GetClosedDeals()

    def get_candles2(self, active, period, start_time=None, count=6000, count_request=1):
        try:
            if start_time is None:
                time_sync = self.get_server_timestamp()
                time_red = self.last_time(time_sync, period)
            else:
                time_red = start_time
                time_sync = self.get_server_timestamp()

            all_candles = []

            for _ in range(count_request):
                self.api.history_data = None

                while True:
                    try:
                        self.api.getcandles(active, period, time_red)

                        for i in range(1, 100):
                            if self.api.history_data is None:
                                time.sleep(0.1)
                            elif self.api.history_data is not None or i == 99:
                                break

                        if self.api.history_data is not None:
                            all_candles.extend(self.api.history_data)
                            break

                    except Exception as e:
                        # logger.error(e)
                        global_value.logger(str(e), "ERROR")

                all_candles = sorted(all_candles, key=lambda x: x["time"])
            if period > 30:
                for i in range(0, len(all_candles)):
                    del all_candles[i]['symbol_id']
                    del all_candles[i]['asset']

                self.api.history_data = None
                ext_candles = []
                while True:
                    try:
                        self.api.getcandles(active, 30, time_red)

                        for i in range(1, 100):
                            if self.api.history_data is None:
                                time.sleep(0.1)
                            elif self.api.history_data is not None or i == 99:
                                break

                        if self.api.history_data is not None:
                            ext_candles.extend(self.api.history_data)
                            break

                    except Exception as e:
                        # logging.error(e)
                        global_value.logger(str(e), "ERROR")

                ext_candles = sorted(ext_candles, key=lambda x: x["time"])
                ext_df = pd.DataFrame(ext_candles)
                ext_df = ext_df.sort_values(by='time').reset_index(drop=True)
                ext_df['time'] = pd.to_datetime(ext_df['time'], unit='s', utc=True)
                ext_df.set_index('time', inplace=True)
                ext_df.index = ext_df.index.floor('1s')
                ext_resampled = ext_df['price'].resample(f'{period}s').ohlc()
                ext_resampled.reset_index(inplace=True)

            df_candles = pd.DataFrame(all_candles)

            df_candles = df_candles.sort_values(by='time').reset_index(drop=True)
            df_candles['time'] = pd.to_datetime(df_candles['time'], unit='s', utc=True)
            df_candles.set_index('time', inplace=True)
            df_candles.index = df_candles.index.floor('1s')

            if period < 60:
                df_resampled = df_candles['price'].resample(f'{period}s').ohlc()
                df_resampled.reset_index(inplace=True)

                return df_resampled
            elif period > 30:
                df_candles.reset_index(inplace=True)
                ts = datetime.timestamp(df_candles.loc[len(df_candles)-1]['time'])
                for i in range(0, len(ext_resampled)):
                    ts2 = datetime.timestamp(ext_resampled.loc[i]['time'])
                    if ts2 > ts:
                        data = {'time': ext_resampled.loc[i]['time'], 'open': ext_resampled.loc[i]['open'], 'close': ext_resampled.loc[i]['close'], 'high': ext_resampled.loc[i]['high'], 'low': ext_resampled.loc[i]['low']}
                        df_candles = df_candles._append(data, ignore_index = True)
                df_candles.reset_index(inplace=True)
                return df_candles
            else:
                df_candles.reset_index(inplace=True)
                return df_candles

        except:
            # print("No except")
            global_value.logger("No except", "DEBUG")
            return None

    @staticmethod
    def process_data_history(data, period):
        df = pd.DataFrame(data['history'], columns=['timestamp', 'price'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        df['minute_rounded'] = df['datetime'].dt.floor(f'{period / 60}min')

        ohlcv = df.groupby('minute_rounded').agg(
            open=('price', 'first'),
            high=('price', 'max'),
            low=('price', 'min'),
            close=('price', 'last')
        ).reset_index()

        ohlcv['time'] = ohlcv['minute_rounded'].apply(lambda x: int(x.timestamp()))
        ohlcv = ohlcv.drop(columns='minute_rounded')

        ohlcv = ohlcv.iloc[:-1]

        ohlcv_dict = ohlcv.to_dict(orient='records')

        return ohlcv_dict

    @staticmethod
    def process_candle(candle_data, period):
        data_df = pd.DataFrame(candle_data)
        data_df.sort_values(by='time', ascending=True, inplace=True)
        data_df.drop_duplicates(subset='time', keep="first", inplace=True)
        data_df.reset_index(drop=True, inplace=True)
        data_df.ffill(inplace=True)

        diferencas = data_df['time'].diff()
        diff = (diferencas[1:] == period).all()
        return data_df, diff

    def change_symbol(self, active, period):
        return self.api.change_symbol(active, period)

    def sync_datetime(self):
        return self.api.synced_datetime

    def get_candles(self, active, period, start_time=None, count=6000, count_request=1):
        try:
            if start_time is None:
                time_sync = self.get_server_timestamp()
                time_red = self.last_time(time_sync, period)
            else:
                time_red = start_time
                time_sync = self.get_server_timestamp()

            all_candles = []

            self.api.history_new = None

            while True:
                try:
                    self.api.change_symbol(active, period)

                    for i in range(1, 100):
                        if self.api.history_new is None:
                            time.sleep(0.1)
                        elif self.api.history_new is not None or i == 99:
                            break

                    if self.api.history_new is not None:
                        his = self.api.history_new
                        break

                except Exception as e:
                    # logging.error(e)
                    global_value.logger(str(e), "ERROR")
            c0, c1 = [], []
            if period < 60:
                self.api.history_data = None
                #time_red = his['history'][0][0]

                while True:
                    try:
                        self.api.getcandles(active, period, time_red)

                        for i in range(1, 100):
                            if self.api.history_data is None:
                                time.sleep(0.1)
                            elif self.api.history_data is not None or i == 99:
                                break

                        if self.api.history_data is not None:
                            c1.extend(self.api.history_data)
                            break

                    except Exception as e:
                        # logger.error(e)
                        global_value.logger(str(e), "ERROR")

            if len(his['candles']) > 0:
                for can in his['candles']:
                    c = {'time': can[0], 'open': can[1], 'high': can[3], 'low': can[4], 'close': can[2]}
                    c0.append(c)
                c0 = sorted(c0, key=lambda x: x["time"])
            for hist in his['history']:
                h = {'time': hist[0], 'price': hist[1]}
                c1.append(h)
            c1 = sorted(c1, key=lambda x: x["time"])
            if active in global_value.pairs:
                global_value.pairs[active]['history'] = c1
                if len(c0) > 0:
                    df = pd.DataFrame(c0)
                    df = df.sort_values(by='time').reset_index(drop=True)
                    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
                    df.set_index('time', inplace=True)
                    df.reset_index(inplace=True)
                    global_value.pairs[active]['dataframe'] = df
            return True

            df1 = pd.DataFrame(c1)
            df1 = df1.sort_values(by='time').reset_index(drop=True)
            df1['time'] = pd.to_datetime(df1['time'], unit='s', utc=True)
            df1.set_index('time', inplace=True)

            df = df1['price'].resample(f'{period}s').ohlc()
            df.reset_index(inplace=True)

            ts = datetime.timestamp(df.loc[0]['time'])
            for x in range(0, len(df0)):
                ts2 = datetime.timestamp(df0.loc[x]['time'])
                if ts2 < ts:
                    df = df._append(df0.loc[x], ignore_index = True)
                else:
                    break
            df = df.sort_values(by='time').reset_index(drop=True)
            df.set_index('time', inplace=True)
            df.reset_index(inplace=True)

            return df

            for _ in range(count_request):
                self.api.history_data = None

                while True:
                    try:
                        self.api.getcandles(active, period, time_red)

                        for i in range(1, 100):
                            if self.api.history_data is None:
                                time.sleep(0.1)
                            elif self.api.history_data is not None or i == 99:
                                break

                        if self.api.history_data is not None:
                            all_candles.extend(self.api.history_data)
                            break

                    except Exception as e:
                        # logging.error(e)
                        global_value.logger(str(e), "ERROR")

                all_candles = sorted(all_candles, key=lambda x: x["time"])

                if all_candles:
                    time_red = all_candles[0]["time"]

            df_candles = pd.DataFrame(all_candles)

            df_candles = df_candles.sort_values(by='time').reset_index(drop=True)
            df_candles['time'] = pd.to_datetime(df_candles['time'], unit='s', utc=True)
            df_candles.set_index('time', inplace=True)
            df_candles.index = df_candles.index.floor('1s')

            df_resampled = df_candles['price'].resample(f'{period}s').ohlc()

            df_resampled.reset_index(inplace=True)

            return df_resampled
        except:
            # print("In except")
            global_value.logger("In except", "DEBUG")
            return None
