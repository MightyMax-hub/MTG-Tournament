from flask import Flask, redirect, Response, request

app = Flask(__name__)
LAN_IP = "192.168.10.101"

@app.before_request
def handle_captive_portal():
    host = request.host.lower()
    path = request.path

     # 1. Wenn das Gerät BEREITS auf Port 5000 zugreift, ignorieren (Sicherheitsanker)
    if "5000" in host:
        return None

    # 2. Wenn das Gerät unseren Wunschnamen auf Port 80 aufruft,
    # leiten wir es direkt auf das echte Turnier (Port 5000) weiter.
    if "tournament.local" in host or "tournament-manager" in host or LAN_IP in host:
        return redirect(f"http://tournament.local:5000{path}", code=302)

    # 3. RADIKALER CATCH-ALL: Jede fremde Domain (google.com etc.)
    # wird hart auf unseren Wunschnamen umgeleitet, um das Portal zu erzwingen!
    return redirect("http://tournament.local", code=302)

if __name__ == '__main__':
    # Wir binden Flask EXKLUSIV an die LAN-IP auf Port 80.
    # Dadurch bleibt Ihr Heim-WLAN zu 100% unberührt!
    app.run(host=LAN_IP, port=80)
