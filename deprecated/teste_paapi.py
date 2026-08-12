import requests

TOKEN = "Atc|MQICICdyVBjZQl4WSBxbYJXgeLBdY1_kChM6VP5rvE6f1_5LCHgk68BgNBc_hKLMsjkqZsxO2DqiRZjegku98JU0hVjfubVFoHFbCJUTaMROgLwFJz9PeUp2BXdo_8PyAGjm0CwrQ3R-xAlC3rkD53OewbGV3pjY7E0N9zMcYKJbp_Sdx9K905neOg2Gbq7zQ_2RaeL_ha7ZEg96UAtGyESnJ-MDnrFqpOVpfMbmP-wDhOdWMX6-gVVOkz5ic2vA4-iGX78"

url = "https://creatorsapi.amazon/catalog/v1/getItems"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "x-marketplace": "www.amazon.com.br"
}

payload = {
    "itemIds": [
        "6528101965"
    ],
    "partnerTag": "bibliotecan0c-20",
    "partnerType": "Associates",
    "resources": [
        "itemInfo.title",
        "offersV2.listings.price"
    ]
}

response = requests.post(
    url,
    headers=headers,
    json=payload
)

print(response.status_code)
print(response.text)