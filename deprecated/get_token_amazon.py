import requests

APPLICATION_ID = "bibliotecan0c-20.livros_by_mands"
CREDENTIAL_ID = "amzn1.application-oa2-client.aa8af5e22c984a19ad80cbe4061a330d"
SECRET = "amzn1.oa2-cs.v1.f53d698e7cfbb41ba6abe15142dd9e6eb2ba54796776c342836565cc8dc441fa"

url = "https://api.amazon.com/auth/o2/token"

payload = {
    "grant_type": "client_credentials",
    "client_id": CREDENTIAL_ID,
    "client_secret": SECRET,
    "scope": "creatorsapi::default"
}

response = requests.post(
    url,
    json=payload,
    headers={
        "Content-Type": "application/json"
    }
)

print(response.status_code)
print(response.text)