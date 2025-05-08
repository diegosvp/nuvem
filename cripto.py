import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time
from datetime import datetime
import telegram
from telegram.error import TelegramError

# Configuração da página
st.set_page_config(page_title="Crypto Trader Pro", layout="wide")
st.title("📊 Análise de Criptomoedas em Tempo Real")

# ===== CONFIGURAÇÃO DO TELEGRAM =====
TELEGRAM_ENABLED = st.sidebar.checkbox("Ativar Alertas no Telegram", value=True)

if TELEGRAM_ENABLED:
    with st.sidebar.expander("🔔 Configurações do Telegram", expanded=True):
        TELEGRAM_BOT_TOKEN = st.text_input("Token do Bot", type="password")
        TELEGRAM_CHAT_ID = st.text_input("Chat ID")
        
        if st.button("Testar Conexão"):
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                st.warning("Preencha o Token e o Chat ID")
            else:
                try:
                    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
                    chat_id = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID.isdigit() else TELEGRAM_CHAT_ID
                    msg = bot.send_message(
                        chat_id=chat_id,
                        text="✅ Conexão testada com sucesso!",
                        parse_mode='Markdown'
                    )
                    st.success("Conexão estabelecida!")
                except Exception as e:
                    st.error(f"Erro: {str(e)}")

def send_telegram_alert(message):
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        chat_id = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID.isdigit() else TELEGRAM_CHAT_ID
        bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        return True
    except Exception as e:
        st.error(f"Falha ao enviar alerta: {str(e)}")
        return False

# ===== CONFIGURAÇÕES =====
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h"], index=0)
EMA_FAST = st.sidebar.slider("EMA Rápida", 5, 20, 9)
EMA_SLOW = st.sidebar.slider("EMA Lenta", 10, 50, 20)
RSI_PERIOD = st.sidebar.slider("Período RSI", 5, 21, 14)
SUPPORT_RESISTANCE_PERIOD = st.sidebar.slider("Período S/R", 10, 50, 20)

# ===== FUNÇÕES DE DADOS =====
@st.cache_data(ttl=60)
def get_binance_data(symbol, interval):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'] + ['ignore']*6)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        st.error(f"Erro ao obter dados para {symbol}: {str(e)[:200]}")
        return pd.DataFrame()

def calculate_indicators(df):
    if df.empty: return df
    
    df = df.copy()
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Suporte/Resistência
    df['resistance'] = df['high'].rolling(SUPPORT_RESISTANCE_PERIOD).max()
    df['support'] = df['low'].rolling(SUPPORT_RESISTANCE_PERIOD).min()
    
    return df

def check_signal(df, symbol):
    if df.empty or len(df) < 50: return None
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    buy_conditions = (
        (current['close'] > current['resistance']) and
        (current['volume'] > df['volume'].rolling(20).mean().iloc[-1] * 1.2) and
        (current['ema_fast'] > current['ema_slow']) and
        (current['rsi'] > 50) and
        (prev['ema_fast'] <= prev['ema_slow'])
    )
    
    if buy_conditions:
        risk = current['close'] - current['support']
        message = f"""
        🚀 *SINAL DE COMPRA - {symbol}* 🚀
        ⏳ Timeframe: {TIMEFRAME}
        💵 Preço: {current['close']:.2f}
        🔴 Stop Loss: {current['support']:.2f}
        🟢 Take Profit 1: {current['close'] + risk:.2f}
        🟢 Take Profit 2: {current['close'] + risk*1.5:.2f}
        📊 Volume: {current['volume']:.0f}
        📈 RSI: {current['rsi']:.1f}
        ⏰ {datetime.now().strftime('%d/%m %H:%M')}
        """
        if send_telegram_alert(message):
            return {
                'type': 'BUY',
                'price': current['close'],
                'sl': current['support'],
                'tp1': current['close'] + risk,
                'tp2': current['close'] + risk*1.5,
                'rsi': current['rsi']
            }
    return None

# ===== GRÁFICOS =====
def create_chart(df, symbol):
    fig = go.Figure()
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Price'
    ))
    
    # EMAs
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['ema_fast'],
        line=dict(color='royalblue', width=1.5),
        name=f'EMA {EMA_FAST}'
    ))
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['ema_slow'],
        line=dict(color='orange', width=1.5),
        name=f'EMA {EMA_SLOW}'
    ))
    
    # Suporte/Resistência
    fig.add_hline(
        y=df['resistance'].iloc[-1],
        line=dict(color='red', width=1, dash='dot'),
        annotation_text=f"Resistência: {df['resistance'].iloc[-1]:.2f}",
        annotation_position="bottom right"
    )
    fig.add_hline(
        y=df['support'].iloc[-1],
        line=dict(color='green', width=1, dash='dot'),
        annotation_text=f"Suporte: {df['support'].iloc[-1]:.2f}",
        annotation_position="top right"
    )
    
    fig.update_layout(
        title=f"{symbol} | {TIMEFRAME} | Último: {df['close'].iloc[-1]:.2f}",
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=20, r=20, t=60, b=20)
    )
    
    return fig

# ===== APLICAÇÃO PRINCIPAL =====
def main():
    placeholder = st.empty()
    
    while True:
        all_data = {}
        signals = {}
        
        for symbol in SYMBOLS:
            df = get_binance_data(symbol, TIMEFRAME)
            if not df.empty:
                df = calculate_indicators(df)
                all_data[symbol] = df
                signals[symbol] = check_signal(df, symbol)
        
        with placeholder.container():
            # Gráficos em linhas separadas para melhor visualização
            for symbol in SYMBOLS:
                if symbol in all_data:
                    st.plotly_chart(
                        create_chart(all_data[symbol], symbol), 
                        use_container_width=True
                    )
                    
                    if signals.get(symbol):
                        st.success(f"""
                        **{symbol} - Sinal de COMPRA**  
                        **Entrada:** {signals[symbol]['price']:.2f}  
                        **Stop Loss:** {signals[symbol]['sl']:.2f}  
                        **Take Profit 1:** {signals[symbol]['tp1']:.2f}  
                        **Take Profit 2:** {signals[symbol]['tp2']:.2f}  
                        **RSI:** {signals[symbol]['rsi']:.1f}
                        """)
            
            # Dados técnicos
            with st.expander("📊 Detalhes Técnicos"):
                tabs = st.tabs(SYMBOLS)
                for idx, symbol in enumerate(SYMBOLS):
                    with tabs[idx]:
                        if symbol in all_data:
                            st.dataframe(
                                all_data[symbol][['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                                'ema_fast', 'ema_slow', 'rsi', 'resistance', 'support']].tail(10),
                                height=300,
                                use_container_width=True
                            )
        
        time.sleep(60)
        st.rerun()

if __name__ == "__main__":
    main()