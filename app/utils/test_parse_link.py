from app.utils.parse_link import extract_asin


if __name__ == "__main__":
    samples = [
        "https://www.amazon.com.br/dp/6528101965",
        "https://www.amazon.com.br/gp/product/6528101965",
        "https://www.amazon.com.br/Produto-Teste/6528101965",
        "https://example.com/product/6528101965",
    ]

    for sample in samples:
        print(sample, "->", extract_asin(sample))
