import os
import json
import requests

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, date, time

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    shares_index = db.execute(
        "SELECT symbol, name, SUM(shares) FROM shares WHERE user_id = :user_id GROUP BY symbol HAVING SUM(shares) > 0 ", user_id=session["user_id"])

    i = 0
    sum_shares = 0
    # symbol_list = []
    # price_list = []

    for list in shares_index:
        symbol_info = lookup(list["symbol"])
        if symbol_info is None:
            return apology("invalid symbol or gate closed", 403)
        sh_price = symbol_info["price"]

        sh_qty = list["SUM(shares)"]
        sum = sh_qty * sh_price
        shares_index[i]["price"] = usd(sh_price)
        shares_index[i].update({'shares_price': usd(sum)})
        sum_shares += sum
        sum = 0
        i += 1

    session["shares_index"] = shares_index

    cash_in = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = cash_in[0]["cash"]
    session["cash"] = usd(cash)
    session["total"] = usd(cash + sum_shares)
    return render_template("index.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("symbol missing", 400)
        elif not request.form.get("shares"):
            return apology("shares missing", 400)

        symbol_info = lookup(request.form.get("symbol"))
        if symbol_info is None:
            return apology("invalid symbol", 400)

        session["name"] = symbol_info['name']
        session["symbol"] = symbol_info['symbol']
        session["price"] = usd(symbol_info['price'])
        shares_f = request.form.get("shares")
        if not int(shares_f):
            return apology("shares must be positive", 400)
        session["shares"] = shares_f

        cash_in = db.execute(
            "SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

        cash = cash_in[0]["cash"]
        if cash < symbol_info['price']:
            return apology("can't afford", 400)

        shares_price = symbol_info['price'] * int(session["shares"])
        session["shares_price"] = usd(shares_price)

        cash -= shares_price
        db.execute("UPDATE users SET cash=? WHERE id=?", (cash, session["user_id"]))
        db.execute("INSERT INTO shares (user_id, symbol, name, shares, price, status, date) VALUES (?,?,?,?,?,?,?)",
                   session["user_id"], session["symbol"], session["name"], session["shares"], symbol_info['price'], 1, datetime.now())

        # Bought !!! to HTML
        shares_in = db.execute(
            "SELECT symbol, name, SUM(shares) FROM shares WHERE user_id = :user_id GROUP BY symbol HAVING SUM(shares) > 0 ", user_id=session["user_id"])
        i = 0
        sum_shares = 0
        for list in shares_in:
            symbol_info = lookup(list["symbol"])
            sh_qty = list["SUM(shares)"]
            sh_price = symbol_info["price"]
            shares_in[i].update({'price': usd(sh_price)})
            sum = sh_qty * sh_price
            shares_in[i].update({'shares_price': usd(sum)})
            sum_shares += sum
            sum = 0
            i += 1
        session["shares_in"] = shares_in
        session["cash"] = usd(cash)
        session["total"] = usd(cash + sum_shares)
        return render_template("bought.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    if request.method == "GET":
        username = request.args.get("username")
    if len(username) < 1:
        return jsonify(False)

    users = db.execute("SELECT username FROM users")

    for list in users:
        if list["username"] == username:
            return jsonify(False)

    return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    sh_history = db.execute("SELECT symbol, shares, price, date FROM shares WHERE user_id=:user_id", user_id=session["user_id"])
    session["sh_history"] = sh_history
    return render_template("history.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):

            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "GET":
        return render_template("quote.html")
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("symbol missing", 400)

        symbol_info = lookup(request.form.get("symbol"))
        if symbol_info is None:
            return apology("invalid symbol", 400)
        session["name"] = symbol_info['name']
        session["symbol"] = symbol_info['symbol']
        session["price"] = usd(symbol_info['price'])
        return render_template("quoted.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 400)

        # Пользователь прислал данные из формы регистрации, проверяем и
        # регистрируем его в базе даннных и редиректим на главную страницу
        else:
            username = request.form.get("username")
            users = db.execute("SELECT username FROM users")

            for list in users:
                if list["username"] == username:
                    return apology("Username is not available", 400)
            password = request.form.get("password")

            result = db.execute("INSERT INTO users (username, hash) VALUES (?,?)", username, generate_password_hash(password))
            session["user_id"] = result
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        sh_symbol = db.execute(
            "SELECT symbol FROM shares WHERE user_id=:user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id=session["user_id"])
        session["sh_symbol"] = sh_symbol
        return render_template("sell.html")
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("symbol missing", 403)
        elif not request.form.get("shares"):
            return apology("shares missing", 403)
        elif int(request.form.get("shares")) < 1:
            return apology("shares must be positive", 403)

    shares_for_sell = db.execute(
        "SELECT symbol, name, SUM(shares) FROM shares WHERE user_id=:user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id=session["user_id"])

    if len(shares_for_sell) < 1:
        return apology("no shares for sell", 403)

    ind = 0
    sum_shares = 0

    shares = int(request.form.get("shares"))

    # sell shares
    for list in shares_for_sell:
        shares_after = list["SUM(shares)"]

        symbol_info = lookup(list["symbol"])

        if request.form.get("symbol").upper() == list["symbol"] and shares > list["SUM(shares)"]:
            return apology("Too many shares", 400)
        elif request.form.get("symbol").upper() == list["symbol"]:
            shares_after -= shares
            sum_sell = symbol_info["price"] * shares
            cash_db = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
            cash_after = cash_db[0]["cash"] + sum_sell
            db.execute("UPDATE users SET cash=? WHERE id=?", (cash_after, session["user_id"]))
            db.execute("INSERT INTO shares (user_id, symbol, name, shares, price, status, date) VALUES (?,?,?,?,?,?,?)",
                       session["user_id"], list["symbol"], list["name"], - shares, symbol_info['price'], 1, datetime.now())

        # SOLD !!! to HTML
        if shares_after == 0:
            del shares_for_sell[ind]
            if len(shares_for_sell) == 0 or ind == len(shares_for_sell):
                continue
            else:
                symbol_info = lookup(shares_for_sell[ind]["symbol"])
                shares_after = shares_for_sell[ind]["SUM(shares)"]
        shares_for_sell[ind]["SUM(shares)"] = shares_after
        sum = int(list["SUM(shares)"]) * symbol_info["price"]
        sum_shares += sum
        shares_for_sell[ind].update({'price': usd(symbol_info["price"])})
        shares_for_sell[ind].update({'shares_price': usd(sum)})
        ind += 1

    session["shares_sold"] = shares_for_sell

    cash_in = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = cash_in[0]["cash"]
    session["cash"] = usd(cash)
    session["total"] = usd(cash + sum_shares)
    return render_template("sold.html")


@app.route("/pwdchange", methods=["GET", "POST"])
# @login_required
def pwdchange():
    if request.method == "GET":
        return render_template("pwdchange.html")

    if request.method == "POST":
        # Ensure password was submitted
        if not request.form.get("password_new"):
            return apology("must provide password", 400)

        password_new = request.form.get("password_new")

        rows = db.execute("SELECT hash FROM users WHERE id = :user_id", user_id=session["user_id"])

        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid user password", 403)

        db.execute("UPDATE users SET hash=? WHERE id=?", (generate_password_hash(password_new), session["user_id"]))

    return redirect("/login")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)