# api.py
import os
import threading
from fastapi import FastAPI, HTTPException
# Lazy-import PySpark components at runtime to avoid import-time crashes
spark = None

def get_spark():
    """Return a SparkSession singleton, creating it on first use.

    Raises ImportError if pyspark isn't available so the FastAPI process
    can still start and return useful errors from endpoints instead of
    crashing at import time.
    """
    global spark
    if spark is not None:
        return spark
    try:
        import sys
        # Ensure PySpark uses the same Python interpreter (Windows commonly lacks `python3`)
        os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
        os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
        # Also set executor env so worker processes use the same interpreter
        os.environ.setdefault("PYSPARK_SUBMIT_ARGS", "")
        from pyspark.sql import SparkSession
    except Exception as e:
        raise ImportError(f"pyspark is required but failed to import or configure: {e}")

    # Configure Spark to use the current Python executable and enable fault handlers
    try:
        spark = (
            SparkSession.builder
            .appName("StockPredictionAPI")
            .config("spark.pyspark.python", sys.executable)
            .config("spark.pyspark.driver.python", sys.executable)
            .config("spark.executorEnv.PYSPARK_PYTHON", sys.executable)
            .config("spark.sql.execution.pyspark.udf.faulthandler.enabled", "true")
            .config("spark.python.worker.faulthandler.enabled", "true")
            .config("spark.python.worker.reuse", "false")
            .getOrCreate()
        )
    except Exception as e:
        msg = str(e)
        # Detect common JVM startup failure and give an actionable error
        if "JAVA_GATEWAY_EXITED" in msg or "Java gateway process exited" in msg or "CreateProcess error=2" in msg:
            raise ImportError(
                "failed to create SparkSession: Java gateway failed to start. "
                "This usually means Java is not installed/configured for PySpark on Windows.\n"
                "Steps to fix:\n"
                " 1. Install a JDK (Adoptium Temurin or OpenJDK 11/17).\n"
                " 2. Set the JAVA_HOME environment variable to the JDK installation path.\n"
                " 3. Add %JAVA_HOME%\\bin to your PATH so `java -version` works in PowerShell.\n"
                " 4. Restart your terminal/IDE and re-run the server.\n"
                "Quick checks you can run in PowerShell:\n"
                "  > java -version\n"
                "  > echo $env:JAVA_HOME\n"
                "If you want, I can add a lightweight pandas/scikit-learn fallback so the API can run without Java/Spark."
            )
        raise ImportError(f"failed to create SparkSession with configured python: {e}")
    return spark
import pandas as pd
import yfinance as yf
import shutil
import datetime
from typing import Optional

# ------------------ CONFIG ------------------
MODEL_DIR = "./model"
MODEL_PATH = os.path.join(MODEL_DIR, "gbt_model")
CACHE_DIR = "./cache"
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

app = FastAPI(title="Stock Prediction API")

# ------------------ SPARK ------------------
# Note: Spark session created lazily by `get_spark()`

# ------------------ DATA LOADER ------------------
def get_stock_data(ticker: str, period: str = "2y"):
    import pandas as pd
    import os
    import yfinance as yf

    ticker = ticker.upper()
    cache_file = os.path.join(CACHE_DIR, f"{ticker}_{period}.csv")

    # Load from cache if exists
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)

        # Ensure 'date' column exists for consistency
        df.columns = [c.lower() for c in df.columns]
        # Normalize ticker-specific suffixes: e.g., 'close_aapl' -> 'close'
        t_low = ticker.lower()
        new_cols = []
        for c in df.columns:
            if isinstance(c, str) and c.endswith(f"_{t_low}"):
                new_cols.append(c[: - (len(t_low) + 1)])
            else:
                new_cols.append(c)
        df.columns = new_cols
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        else:
            # If somehow no date column, try index
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'date'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
        return df

    # Download from yfinance
    df = yf.download(ticker, period=period, auto_adjust=False)

    # yfinance may return (DataFrame, info) or other structures; normalize to DataFrame
    if isinstance(df, tuple) and len(df) > 0:
        df = df[0]
    if isinstance(df, dict):
        # sometimes returns a dict of DataFrames indexed by ticker
        if ticker in df:
            df = df[ticker]
        else:
            # pick first DataFrame value
            vals = [v for v in df.values() if hasattr(v, "columns")]
            df = vals[0] if vals else None

    if df is None:
        return None

    # Ensure we have a DataFrame
    if not hasattr(df, "columns"):
        return None

    # Handle MultiIndex columns (e.g., when multiple tickers are requested)
    if hasattr(df.columns, "nlevels") and getattr(df.columns, "nlevels", 1) > 1:
        df.columns = ["_".join([str(c) for c in col if c is not None and c != ""]) for col in df.columns.values]

    # Normalize ticker-specific suffixes for downloaded data as well
    t_low = ticker.lower()
    new_cols = []
    for c in df.columns:
        if isinstance(c, str) and c.endswith(f"_{t_low}"):
            new_cols.append(c[: - (len(t_low) + 1)])
        else:
            new_cols.append(c)
    df.columns = new_cols

    if getattr(df, "empty", True):
        return None

    df.reset_index(inplace=True)  # 'Date' column created (or preserve existing index)
    df.columns = [c.lower() for c in df.columns]  # lowercase all columns
    df.to_csv(cache_file, index=False)
    return df



# ------------------ TRAIN MODEL ------------------
def train_model_for_ticker(ticker: str, overwrite: bool = False):
    ticker = ticker.upper()
    model_dir = f"{MODEL_PATH}_{ticker}"
    if os.path.exists(model_dir) and not overwrite:
        return model_dir

    pdf = get_stock_data(ticker, "2y")
    if pdf is None or pdf.empty:
        raise ValueError("No data available for ticker")

    # Ensure numeric types
    for col_name in ["close"]:
        pdf[col_name] = pd.to_numeric(pdf[col_name], errors="coerce")
    pdf.dropna(subset=["close"], inplace=True)

    # Try to train with Spark; if Spark/Java isn't available, fall back to scikit-learn
    try:
        spark = get_spark()
        from pyspark.sql.window import Window
        from pyspark.sql.functions import lag, avg
        from pyspark.ml.feature import VectorAssembler
        from pyspark.ml.regression import GBTRegressor

        sdf = spark.createDataFrame(pdf)
        w = Window.orderBy("date")

        feat = (
            sdf.withColumn("lag1", lag("close", 1).over(w))
               .withColumn("lag2", lag("close", 2).over(w))
               .withColumn("ma5", avg("close").over(w.rowsBetween(-4, 0)))
               .withColumn("ma10", avg("close").over(w.rowsBetween(-9, 0)))
               .dropna()
        )

        assembler = VectorAssembler(inputCols=["lag1", "lag2", "ma5", "ma10"], outputCol="features")
        data_ml = assembler.transform(feat).select("close", "features")
        train, test = data_ml.randomSplit([0.8, 0.2], seed=42)

        model = GBTRegressor(labelCol="close", featuresCol="features", maxIter=30, maxDepth=5)
        gbt_model = model.fit(train)

        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
        gbt_model.write().overwrite().save(model_dir)
        return model_dir

    except ImportError:
        # Spark not available; fallback to scikit-learn
        try:
            from sklearn.ensemble import GradientBoostingRegressor
            from sklearn.model_selection import train_test_split
            from joblib import dump
        except Exception as e:
            raise ImportError(f"scikit-learn and joblib are required for fallback training: {e}")

        # Create lag/MA features in pandas
        pdf2 = pdf.copy()
        pdf2 = pdf2.sort_values("date")
        pdf2["lag1"] = pdf2["close"].shift(1)
        pdf2["lag2"] = pdf2["close"].shift(2)
        pdf2["ma5"] = pdf2["close"].rolling(5).mean()
        pdf2["ma10"] = pdf2["close"].rolling(10).mean()
        pdf2.dropna(subset=["lag1", "lag2", "ma5", "ma10", "close"], inplace=True)

        X = pdf2[["lag1", "lag2", "ma5", "ma10"]].values
        y = pdf2["close"].values

        if len(y) < 10:
            raise ValueError("Not enough data to train sklearn fallback")

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        sk_model = GradientBoostingRegressor(n_estimators=100, max_depth=5)
        sk_model.fit(X_train, y_train)

        sklearn_path = os.path.join(MODEL_DIR, f"sklearn_gbt_{ticker}.joblib")
        dump(sk_model, sklearn_path)
        return sklearn_path

def load_model(ticker: str):
    ticker = ticker.upper()
    model_dir = f"{MODEL_PATH}_{ticker}"
    # Prefer Spark model if available
    if os.path.exists(model_dir):
        try:
            from pyspark.ml.regression import GBTRegressionModel
            return (GBTRegressionModel.load(model_dir), "spark")
        except Exception:
            # Fall through to sklearn loader
            pass

    sklearn_path = os.path.join(MODEL_DIR, f"sklearn_gbt_{ticker}.joblib")
    if os.path.exists(sklearn_path):
        try:
            from joblib import load
        except Exception as e:
            raise ImportError(f"joblib is required to load sklearn models: {e}")
        return (load(sklearn_path), "sklearn")

    return (None, None)

# ------------------ STARTUP EVENT ------------------
@app.on_event("startup")
def startup_event():
    def background_train():
        try:
            print("Background training AAPL started...")
            train_model_for_ticker("AAPL", overwrite=False)
            print("Background training AAPL completed.")
        except Exception as e:
            print("Background training error:", str(e))
    thread = threading.Thread(target=background_train, daemon=True)
    thread.start()

# ------------------ PREDICTION ENDPOINT ------------------
@app.get("/predict")
def predict(ticker: str):
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker required")
    ticker = ticker.upper()

    model, model_type = load_model(ticker)
    if model is None:
        try:
            train_model_for_ticker(ticker)
            model, model_type = load_model(ticker)
        except ValueError:
            raise HTTPException(status_code=404, detail="No data for ticker")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    pdf = get_stock_data(ticker, "3mo")
    if pdf is None or pdf.empty or len(pdf) < 12:
        raise HTTPException(status_code=400, detail="Insufficient data")

    for col_name in ["close"]:
        pdf[col_name] = pd.to_numeric(pdf[col_name], errors="coerce")
    pdf.dropna(subset=["close"], inplace=True)

    # If we have a Spark model, use the existing Spark pipeline
    if model_type == "spark":
        try:
            spark = get_spark()
            from pyspark.sql.window import Window
            from pyspark.sql.functions import lag, avg
            from pyspark.ml.feature import VectorAssembler
        except ImportError:
            raise HTTPException(status_code=500, detail="PySpark required for Spark model prediction")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PySpark error for prediction: {e}")

        sdf = spark.createDataFrame(pdf)
        w = Window.orderBy("date")
        feat = (
            sdf.withColumn("lag1", lag("close", 1).over(w))
               .withColumn("lag2", lag("close", 2).over(w))
               .withColumn("ma5", avg("close").over(w.rowsBetween(-4, 0)))
               .withColumn("ma10", avg("close").over(w.rowsBetween(-9, 0)))
               .dropna()
        )

        assembler = VectorAssembler(inputCols=["lag1", "lag2", "ma5", "ma10"], outputCol="features")
        data_ml = assembler.transform(feat).orderBy("date", ascending=False)

        if data_ml.count() == 0:
            raise HTTPException(status_code=400, detail="Not enough data for prediction")

        row = data_ml.first()
        pred_df = spark.createDataFrame([(row["features"],)], ["features"])
        prediction = model.transform(pred_df).collect()[0]["prediction"]

        return {
            "ticker": ticker,
            "date_used": str(row["date"]),
            "actual_close": float(row["close"]),
            "prediction": float(prediction),
            "model_dir": f"{MODEL_PATH}_{ticker}"
        }

    # Otherwise, use sklearn model (pandas)
    if model_type == "sklearn":
        try:
            import numpy as np
        except Exception:
            raise HTTPException(status_code=500, detail="numpy is required for sklearn prediction")

        pdf2 = pdf.copy()
        pdf2 = pdf2.sort_values("date")
        pdf2["lag1"] = pdf2["close"].shift(1)
        pdf2["lag2"] = pdf2["close"].shift(2)
        pdf2["ma5"] = pdf2["close"].rolling(5).mean()
        pdf2["ma10"] = pdf2["close"].rolling(10).mean()
        pdf2.dropna(subset=["lag1", "lag2", "ma5", "ma10", "close"], inplace=True)

        if pdf2.shape[0] == 0:
            raise HTTPException(status_code=400, detail="Not enough data for prediction")

        last = pdf2.iloc[-1]
        X = np.array([[last["lag1"], last["lag2"], last["ma5"], last["ma10"]]])

        try:
            prediction = model.predict(X)[0]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"sklearn prediction failed: {e}")

        return {
            "ticker": ticker,
            "date_used": str(last["date"]),
            "actual_close": float(last["close"]),
            "prediction": float(prediction),
            "model_dir": os.path.join(MODEL_DIR, f"sklearn_gbt_{ticker}.joblib")
        }

    raise HTTPException(status_code=500, detail="No model available for prediction")


@app.get("/analysis")
def analysis(ticker: str, days: Optional[int] = 7):
    """Return a short article-style analysis: predicted price after `days`, expected return,
    and suggested buy/sell dates/prices. Uses Spark model when available, else sklearn fallback.
    """
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker required")
    ticker = ticker.upper()

    model, model_type = load_model(ticker)
    if model is None:
        try:
            train_model_for_ticker(ticker)
            model, model_type = load_model(ticker)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    pdf = get_stock_data(ticker, "3mo")
    if pdf is None or pdf.empty:
        raise HTTPException(status_code=404, detail="No recent data available for ticker")

    # normalize and sort
    pdf = pdf.sort_values("date")
    last_date = pd.to_datetime(pdf.iloc[-1]["date"]) if "date" in pdf.columns else pd.Timestamp.today()
    last_close = float(pdf.iloc[-1]["close"]) if "close" in pdf.columns else None

    if last_close is None:
        raise HTTPException(status_code=500, detail="Could not determine last close price")

    predicted_7 = None
    predicted_1 = None
    method_used = model_type

    # If sklearn model, do iterative prediction for `days`
    if model_type == "sklearn":
        try:
            import numpy as np
        except Exception:
            raise HTTPException(status_code=500, detail="numpy required for sklearn prediction")

        series = list(pdf["close"].astype(float).values)
        pred_dates = []
        preds = []
        for i in range(days):
            lag1 = series[-1]
            lag2 = series[-2] if len(series) >= 2 else series[-1]
            ma5 = float(pd.Series(series[-5:]).mean()) if len(series) >= 1 else series[-1]
            ma10 = float(pd.Series(series[-10:]).mean()) if len(series) >= 1 else series[-1]
            X = np.array([[lag1, lag2, ma5, ma10]])
            try:
                p = float(model.predict(X)[0])
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"sklearn iterative prediction failed: {e}")
            preds.append(p)
            series.append(p)
            pred_dates.append((last_date + pd.Timedelta(days=i+1)).strftime("%Y-%m-%d"))

        predicted_1 = preds[0]
        predicted_7 = preds[min(days, len(preds)) - 1]

    elif model_type == "spark":
        # Use Spark to predict one-step then extrapolate linearly for N days
        try:
            spark = get_spark()
            from pyspark.sql.window import Window
            from pyspark.sql.functions import lag, avg
            from pyspark.ml.feature import VectorAssembler
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PySpark required for Spark prediction: {e}")

        sdf = spark.createDataFrame(pdf)
        w = Window.orderBy("date")
        feat = (
            sdf.withColumn("lag1", lag("close", 1).over(w))
               .withColumn("lag2", lag("close", 2).over(w))
               .withColumn("ma5", avg("close").over(w.rowsBetween(-4, 0)))
               .withColumn("ma10", avg("close").over(w.rowsBetween(-9, 0)))
               .dropna()
        )
        assembler = VectorAssembler(inputCols=["lag1", "lag2", "ma5", "ma10"], outputCol="features")
        data_ml = assembler.transform(feat).orderBy("date", ascending=False)
        if data_ml.count() == 0:
            raise HTTPException(status_code=400, detail="Not enough data for prediction")
        row = data_ml.first()
        pred_df = spark.createDataFrame([(row["features"],)], ["features"])
        predicted_1 = model.transform(pred_df).collect()[0]["prediction"]
        # linear extrapolation
        delta = predicted_1 - last_close
        predicted_7 = last_close + delta * days

    else:
        raise HTTPException(status_code=500, detail="Unknown model type")

    # Formulate article
    try:
        pct_return = (predicted_7 - last_close) / last_close * 100.0
    except Exception:
        pct_return = None

    buy_date = (last_date + pd.Timedelta(days=0)).strftime("%Y-%m-%d")
    sell_date = (last_date + pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    article = []
    article.append(f"Stock outlook for {ticker} — {buy_date} to {sell_date}")
    article.append("")
    article.append(f"Current closing price (last available): ${last_close:.2f} on {last_date.strftime('%Y-%m-%d')}")
    article.append(f"Model used: {method_used}")
    article.append("")
    article.append(f"Predicted price after {days} day(s): ${predicted_7:.2f}")
    if pct_return is not None:
        sign = "+" if pct_return >= 0 else ""
        article.append(f"Expected return over {days} days: {sign}{pct_return:.2f}%")
    article.append("")

    # Simple actionable guidance
    if pct_return is not None:
        if pct_return > 2.0:
            advice = f"Recommendation: Consider BUY now ({buy_date}) and target SELL on {sell_date} around ${predicted_7:.2f}."
        elif pct_return < -2.0:
            advice = f"Recommendation: Consider SELL / avoid buying; model expects a decline to ${predicted_7:.2f} by {sell_date}."
        else:
            advice = f"Recommendation: Neutral — predicted change is small ({pct_return:.2f}%). Consider holding or using tighter risk controls."
    else:
        advice = "Recommendation: Model output unavailable for clear guidance."

    article.append(advice)
    article.append("")
    article.append("Confidence & notes:")
    article.append("- This article is generated from a statistical model (Spark/sklearn). Forecasts are not guarantees.")
    article.append("- The model uses short-term lag and moving-average features; unexpected news or market events can invalidate the forecast.")
    article.append("- If you need higher confidence, consider running backtests or ensemble models and check implied volatility/market context.")

    return {
        "ticker": ticker,
        "last_date": str(last_date.date()),
        "last_close": float(last_close),
        "predicted_close_in_days": float(predicted_7),
        "expected_return_pct": float(pct_return) if pct_return is not None else None,
        "buy_date": buy_date,
        "sell_date": sell_date,
        "article": "\n".join(article)
    }
