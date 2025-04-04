import time, logging, math, asyncio, json, threading
from datetime import datetime
from pocketoptionapi.stable_api import PocketOption
import pocketoptionapi.global_value as global_value
import talib.abstract as ta
import numpy as np
import pandas as pd
import freqtrade.vendor.qtpylib.indicators as qtpylib

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')

# Session configuration
start_counter = time.perf_counter()

### REAL SSID Format::
#ssid = """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"aa11b2345c67d89e0f1g23456h78i9jk\\";s:10:\\"ip_address\\";s:11:\\"11.11.11.11\\";s:10:\\"user_agent\\";s:111:\\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36\\";s:13:\\"last_activity\\";i:1234567890;}1234a5b678901cd2efghi34j5678kl90","isDemo":0,"uid":12345678,"platform":2}]"""
#demo = False

### DEMO SSID Format::
#ssid = """42["auth",{"session":"abcdefghijklm12nopqrstuvwx","isDemo":1,"uid":12345678,"platform":2}]"""
#demo = True

ssid = """42["auth",{"session":"a:4:{s:10:\\"session_id\\";s:32:\\"aa11b2345c67d89e0f1g23456h78i9jk\\";s:10:\\"ip_address\\";s:11:\\"11.11.11.11\\";s:10:\\"user_agent\\";s:111:\\"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36\\";s:13:\\"last_activity\\";i:1234567890;}1234a5b678901cd2efghi34j5678kl90","isDemo":0,"uid":12345678,"platform":2}]"""
demo = False

min_payout = 90
period = 60
expiration = 60
api = PocketOption(ssid,demo)

# Connect to API
api.connect()


def get_payout():
    try:
        d = global_value.PayoutData
        d = json.loads(d)
        for pair in d:
            #  0,    1,       2,       3,    4, 5,  6,  7,  8, 9, 10, 11, 12, 13,         14,                                                                             15,                                                                                                                 16, 17,     18
            # [5, '#AAPL', 'Apple', 'stock', 2, 50, 60, 30, 3, 0, 170, 0, [], 1743724800, False, [{'time': 60}, {'time': 120}, {'time': 180}, {'time': 300}, {'time': 600}, {'time': 900}, {'time': 1800}, {'time': 2700}, {'time': 3600}, {'time': 7200}, {'time': 10800}, {'time': 14400}], -1, 60, 1743784500],
            if len(pair) == 19:
                if pair[14] == True and pair[5] >= min_payout and "_otc" in pair[1]:
                    p = {}
                    p['payout'] = pair[5]
                    p['type'] = pair[3]
                    global_value.pairs[pair[1]] = p
        return True
    except:
        return False


def get_df():
    try:
        i = 0
        for pair in global_value.pairs:
            i += 1
            df = api.get_candles(pair, period)
            print('%s (%s/%s)' % (str(pair), str(i), str(len(global_value.pairs))))
            time.sleep(1)
        return True
    except:
        return False


def buy(amount, pair, action, expiration):
    print('%s, %s, %s, %s' % (str(amount), str(pair), str(action), str(expiration)))
    result = api.buy(amount=amount, active=pair, action=action, expirations=expiration)
    i = result[1]
    result = api.check_win(i)
    if result:
        print(result)


def make_df(df0, history):
    df1 = pd.DataFrame(history)
    df1 = df1.sort_values(by='time').reset_index(drop=True)
    df1['time'] = pd.to_datetime(df1['time'], unit='s', utc=True)
    df1.set_index('time', inplace=True)

    df = df1['price'].resample(f'{period}s').ohlc()
    df.reset_index(inplace=True)

    if df0 is not None:
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


def accelerator_oscillator(dataframe, fastPeriod=5, slowPeriod=34, smoothPeriod=5):
    ao = ta.SMA(dataframe["hl2"], timeperiod=fastPeriod) - ta.SMA(dataframe["hl2"], timeperiod=slowPeriod)
    ac = ta.SMA(ao, timeperiod=smoothPeriod)
    return ac


def DeMarker(dataframe, Period=14):
    dataframe['dem_high'] = dataframe['high'] - dataframe['high'].shift(1)
    dataframe['dem_low'] = dataframe['low'].shift(1) - dataframe['low']
    dataframe.loc[(dataframe['dem_high'] < 0), 'dem_high'] = 0
    dataframe.loc[(dataframe['dem_low'] < 0), 'dem_low'] = 0

    dem = ta.SMA(dataframe['dem_high'], Period) / (ta.SMA(dataframe['dem_high'], Period) + ta.SMA(dataframe['dem_low'], Period))
    return dem


def vortex_indicator(dataframe, Period=14):
    vm_plus = abs(dataframe['high'] - dataframe['low'].shift(1))
    vm_minus = abs(dataframe['low'] - dataframe['high'].shift(1))

    tr1 = dataframe['high'] - dataframe['low']
    tr2 = abs(dataframe['high'] - dataframe['close'].shift(1))
    tr3 = abs(dataframe['low'] - dataframe['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    sum_vm_plus = vm_plus.rolling(window=Period).sum()
    sum_vm_minus = vm_minus.rolling(window=Period).sum()
    sum_tr = tr.rolling(window=Period).sum()

    vi_plus = sum_vm_plus / sum_tr
    vi_minus = sum_vm_minus / sum_tr

    return vi_plus, vi_minus


def strategie():
    for pair in global_value.pairs:
        if 'history' in global_value.pairs[pair]:
            if 'dataframe' in global_value.pairs[pair]:
                df = make_df(global_value.pairs[pair]['dataframe'], global_value.pairs[pair]['history'])
            else:
                df = make_df(None, global_value.pairs[pair]['history'])

            # Heikinashi
            heikinashi = qtpylib.heikinashi(df)
            df['ha_open'] = heikinashi['open']
            df['ha_close'] = heikinashi['close']
            df['ha_high'] = heikinashi['high']
            df['ha_low'] = heikinashi['low']

            # Accelerator Oscillator Indicator
            df['hl2'] = (df['high'] + df['low']) / 2
            df['ac'] = accelerator_oscillator(df, 5, 34, 5)

            # Aroon, Aroon Oscillator
            df['aroondown'], df['aroonup'] = ta.AROON(df['high'], df['low'], timeperiod=25)

            # DeMarker
            df['dem'] = DeMarker(df, 14)

            # MACD
            df['macd'], df['macdsignal'], df['macdhist'] = ta.MACD(df['ha_close'], 8, 26, 9)

            # Rate of Change
            df['roc'] = ta.ROC(df, timeperiod=10)

            # ADX
            df['adx'] = ta.ADX(df, timeperiod=14)
            df['plus_di'] = ta.PLUS_DI(df, timeperiod=14)
            df['minus_di'] = ta.MINUS_DI(df, timeperiod=14)

            # ATR - Average True Range
            df['atr'] = ta.ATR(df, timeframe=14)

            # Bollinger Bands
            bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(df), window=5, stds=1)
            df['bb_low'] = bollinger['lower']
            df['bb_mid'] = bollinger['mid']
            df['bb_up'] = bollinger['upper']

            # CCI - Commodity Channel Index
            df['cci'] = ta.CCI(df, timeperiod=20)

            # MOM - Momentum
            df['mom'] = ta.MOM(df, timeperiod=10)

            # SAR - Parabolic SAR
            df['sar'] = ta.SAR(df, 0.02, 0.2)

            # Moving Average
            df['ema'] = ta.EMA(df, timeperiod=10)
            df['sma'] = ta.SMA(df, timeperiod=10)
            df['wma'] = ta.WMA(df, timeperiod=10)

            # RSI - Relative Strength Index
            df['rsi'] = ta.RSI(df["close"], timeperiod=14)

            # Stochastic Oscillator
            df['slowk'], df['slowd'] = ta.STOCH(df['high'], df['low'], df['close'], fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)

            # Williams' %R
            df['willr'] = ta.WILLR(df, timeperiod=14)

            # Keltner Channel
            kc = qtpylib.keltner_channel(df, window=14, atrs=2)
            df['kc_upper'] = kc['upper']
            df['kc_lower'] = kc['lower']
            df['kc_mid'] = kc['mid']

            # Vortex
            df['vip'], df['vim'] = vortex_indicator(df, 14)

            # Strategy 1
            # df['ma1'] = ta.SMA(df["close"], timeperiod=5)
            # df['ma2'] = ta.SMA(df["close"], timeperiod=13)
            # df['ma3'] = ta.SMA(df["close"], timeperiod=45)
            # df['rsi'] = ta.RSI(df["close"], timeperiod=5)
            # df['ma12_cross'], df['ma13_cross'], df['ma23_cross'] = 0, 0, 0
            # df['ma1_trend'], df['ma2_trend'], df['ma3_trend'] = 0, 0, 0
            # df.loc[(df['ma1'] > df['ma1'].shift(1)), 'ma1_trend'] = 1
            # df.loc[(df['ma1'] < df['ma1'].shift(1)), 'ma1_trend'] = -1
            # df.loc[(df['ma2'] > df['ma2'].shift(1)), 'ma2_trend'] = 1
            # df.loc[(df['ma2'] < df['ma2'].shift(1)), 'ma2_trend'] = -1
            # df.loc[(df['ma3'] > df['ma3'].shift(1)), 'ma3_trend'] = 1
            # df.loc[(df['ma3'] < df['ma3'].shift(1)), 'ma3_trend'] = -1
            # df.loc[(qtpylib.crossed_above(df['ma1'], df['ma2'])), 'ma12_cross'] = 1
            # df.loc[(qtpylib.crossed_below(df['ma1'], df['ma2'])), 'ma12_cross'] = -1
            # df.loc[(qtpylib.crossed_above(df['ma1'], df['ma3'])), 'ma13_cross'] = 1
            # df.loc[(qtpylib.crossed_below(df['ma1'], df['ma3'])), 'ma13_cross'] = -1
            # df.loc[(qtpylib.crossed_above(df['ma2'], df['ma3'])), 'ma23_cross'] = 1
            # df.loc[(qtpylib.crossed_below(df['ma2'], df['ma3'])), 'ma23_cross'] = -1
            # df['buy'] = 0
            # df.loc[(
            #         (
            #             (df['ma13_cross'] == -1) |
            #             (df['ma23_cross'] == -1)
            #         ) &
            #         (df['ma3_trend'] == -1) &
            #         (df['rsi'] <= 35)
            #     ), 'buy'] = 1
            # df.loc[(
            #         (
            #             (df['ma13_cross'] == 1) |
            #             (df['ma23_cross'] == 1)
            #         ) &
            #         (df['ma3_trend'] == 1) &
            #         (df['rsi'] >= 65)
            #     ), 'buy'] = -1
            # if df.loc[len(df)-1]['buy'] != 0:
            #     t = threading.Thread(target=buy, args=(100, pair, "call" if df.loc[len(df)-1]['buy'] == 1 else "put", 60,))
            #     t.start()

            # # Strategy 2
            # bollinger2 = qtpylib.bollinger_bands(qtpylib.typical_price(df), window=13, stds=2)
            # df['bb_low'] = bollinger2['lower']
            # df['bb_mid'] = bollinger2['mid']
            # df['bb_up'] = bollinger2['upper']
            # df['rsi1'] = ta.RSI(df["close"], timeperiod=5)
            # df['rsi2'] = ta.RSI(df["close"], timeperiod=20)
            # df['buy'] = 0
            # df.loc[(
            #         (df['close'] < df['bb_low']) &
            #         (df['rsi1'] <= 30) &
            #         (df['rsi2'] <= 50)
            #     ), 'buy'] = 1
            # df.loc[(
            #         (df['close'] > df['bb_up']) &
            #         (df['rsi1'] >= 70) &
            #         (df['rsi2'] >= 50)
            #     ), 'buy'] = -1
            # if df.loc[len(df)-1]['buy'] != 0:
            #     t = threading.Thread(target=buy, args=(100, pair, "call" if df.loc[len(df)-1]['buy'] == 1 else "put", 60,))
            #     t.start()

            # Strategy 3
            # heikinashi = qtpylib.heikinashi(df)
            # df['ha_open'] = heikinashi['open']
            # df['ha_close'] = heikinashi['close']
            # df['ha_high'] = heikinashi['high']
            # df['ha_low'] = heikinashi['low']
            # df['ma1'] = ta.SMA(df["ha_close"], timeperiod=5)
            # df['ma2'] = ta.SMA(df["ha_close"], timeperiod=10)
            # macd, macdsignal, macdhist = ta.MACD(df['ha_close'], 8, 26, 9)
            # df['macd'] = macd
            # df['macdsignal'] = macdsignal
            # df['macdhist'] = macdhist
            # df['buy'], df['ma_cross'], df['macd_cross'] = 0, 0, 0
            # df.loc[(qtpylib.crossed_above(df['ma1'], df['ma2'])), 'ma_cross'] = 1
            # df.loc[(qtpylib.crossed_below(df['ma1'], df['ma2'])), 'ma_cross'] = -1
            # df.loc[(qtpylib.crossed_above(df['macd'], df['macdsignal'])), 'macd_cross'] = 1
            # df.loc[(qtpylib.crossed_below(df['macd'], df['macdsignal'])), 'macd_cross'] = -1
            # df.loc[(
            #         (
            #             (df['ma_cross'] == 1) &
            #             (
            #                 (df['macd_cross'] == 1) |
            #                 (df['macd_cross'].shift(1) == 1)
            #             ) &
            #             (df['macdhist'] > 0)
            #         ) |
            #         (
            #             (df['macd_cross'] == 1) &
            #             (
            #                 (df['ma_cross'] == 1) |
            #                 (df['ma_cross'].shift(1) == 1)
            #             ) &
            #             (df['macdhist'] > 0) &
            #             (df['macd'] < 0)
            #         )
            #     ), 'buy'] = 1
            # df.loc[(
            #         (
            #             (df['ma_cross'] == -1) &
            #             (
            #                 (df['macd_cross'] == -1) |
            #                 (df['macd_cross'].shift(1) == -1)
            #             ) &
            #             (df['macdhist'] < 0)
            #         ) |
            #         (
            #             (df['macd_cross'] == -1) &
            #             (
            #                 (df['ma_cross'] == -1) |
            #                 (df['ma_cross'].shift(1) == -1)
            #             ) &
            #             (df['macdhist'] < 0) &
            #             (df['macd'] > 0)
            #         )
            #     ), 'buy'] = -1
            # if df.loc[len(df)-1]['buy'] != 0:
            #     t = threading.Thread(target=buy, args=(100, pair, "call" if df.loc[len(df)-1]['buy'] == 1 else "put", 120,))
            #     t.start()


def prepare():
    try:
        data = get_payout()
        if data:
            data = get_df()
            if data: return True
            else: return False
        else: return False
    except:
        return False


def wait():
    dt = int(datetime(int(datetime.now().year), int(datetime.now().month), int(datetime.now().day), int(datetime.now().hour), int(datetime.now().minute), 0).timestamp())
    if period == 60:
        dt += 60
    elif period == 30:
        if datetime.now().second < 30: dt += 30
        else: dt += 60
    elif period == 15:
        if datetime.now().second >= 45: dt += 60
        elif datetime.now().second >= 30: dt += 45
        elif datetime.now().second >= 15: dt += 30
        else: dt += 15
    elif period == 10:
        if datetime.now().second >= 50: dt += 60
        elif datetime.now().second >= 40: dt += 50
        elif datetime.now().second >= 30: dt += 40
        elif datetime.now().second >= 20: dt += 30
        elif datetime.now().second >= 10: dt += 20
        else: dt += 10
    elif period == 5:
        if datetime.now().second >= 55: dt += 60
        elif datetime.now().second >= 50: dt += 55
        elif datetime.now().second >= 45: dt += 50
        elif datetime.now().second >= 40: dt += 45
        elif datetime.now().second >= 35: dt += 40
        elif datetime.now().second >= 30: dt += 35
        elif datetime.now().second >= 25: dt += 30
        elif datetime.now().second >= 20: dt += 25
        elif datetime.now().second >= 15: dt += 20
        elif datetime.now().second >= 10: dt += 15
        elif datetime.now().second >= 5: dt += 10
        else: dt += 5
    print('====================================')
    print('Sleeping %s Seconds' % str(dt - int(datetime.now().timestamp())))
    return dt - int(datetime.now().timestamp())


def start():
    while global_value.websocket_is_connected is False:
        time.sleep(0.1)
    time.sleep(2)
    prep = prepare()
    if prep:
        while True:
            strategie()
            time.sleep(wait())


if __name__ == "__main__":
    start()
    end_counter = time.perf_counter()
    # rund = math.ceil(end_counter - start_counter)
    print(f'CPU-gebundene Task-Zeit: {end_counter - start_counter} Sekunden')

