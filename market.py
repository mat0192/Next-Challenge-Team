"""Read-only market data. Never modify the shared portfolio on refresh."""
import math
import yfinance as yf


def fetch_quotes(tickers):
    result, errors = {}, []
    for symbol in sorted(set(tickers)):
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period="1mo", auto_adjust=False, actions=False, timeout=12)
            metadata = ticker.get_history_metadata()
            currency = metadata.get("currency")
            close = history["Close"].dropna()
            if close.empty or not math.isfinite(float(close.iloc[-1])) or float(close.iloc[-1]) <= 0:
                raise ValueError("cours absent")
            if currency != "EUR":
                raise ValueError("devise non EUR ou non vérifiée")
            result[symbol] = {"price": float(close.iloc[-1]),
                              "date": close.index[-1].date().isoformat(),
                              "currency": currency, "source": "Yahoo Finance · clôture quotidienne"}
        except Exception:
            errors.append(f"{symbol} : cours EUR indisponible. Renseignez un cours daté dans le portefeuille.")
    return result, errors
