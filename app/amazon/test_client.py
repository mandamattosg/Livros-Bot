from app.amazon.client import AmazonClient


if __name__ == "__main__":
    client = AmazonClient()
    data = client.get_items(["6528101965"])
    print(data)
