# Roadmap de Desenvolvimento - Book Price Bot

## Objetivo

Desenvolver um bot do Telegram que permita ao usuário monitorar preços
de livros da Amazon utilizando a **Creators API (PAAPI)**. O usuário
envia um link do livro, o bot passa a monitorar o preço e envia uma
notificação quando houver queda.

O desenvolvimento será dividido em etapas pequenas e independentes,
priorizando testes locais. Apenas quando toda a lógica estiver validada
localmente será realizada a adaptação para execução em produção no
Railway.

------------------------------------------------------------------------

# Arquitetura Geral

``` text
Usuário
    │
Telegram Bot
    │
Serviços
    ├── Amazon Client (Creators API)
    ├── Product Service
    ├── Notification Service
    ├── Scheduler
    └── Database
            │
        PostgreSQL
```

## Etapa 1 -- Estrutura Inicial

**Objetivo:** criar a estrutura do projeto.

    book-price-bot/
    ├── app/
    │   ├── amazon/
    │   ├── bot/
    │   ├── database/
    │   ├── models/
    │   ├── scheduler/
    │   ├── services/
    │   ├── utils/
    │   ├── config.py
    │   ├── logging.py
    │   └── main.py
    ├── requirements.txt
    ├── .env.example
    └── README.md

**Critérios** - Projeto organizado - Configuração por variáveis de
ambiente - Logging básico

------------------------------------------------------------------------

## Etapa 2 -- Banco de Dados

Criar as tabelas:

-   users
-   products
-   user_products
-   price_history

**Critérios** - Models criados - Migrações funcionando - Banco
inicializado localmente

------------------------------------------------------------------------

## Etapa 3 -- Integração com a Creators API

Criar a classe `AmazonClient`.

Métodos:

-   `get_access_token()`
-   `get_items(asins)`
-   `extract_title()`
-   `extract_price()`
-   `extract_image()`

**Critérios** - Consulta funcionando para um ASIN - Nenhuma lógica de
Telegram ou banco nesta etapa

------------------------------------------------------------------------

## Etapa 4 -- Parser de Links

Aceitar URLs Amazon e extrair o ASIN.

**Critérios** - Função isolada e testada

------------------------------------------------------------------------

## Etapa 5 -- Cadastro de Produtos

Fluxo:

1.  Receber link
2.  Extrair ASIN
3.  Consultar API
4.  Salvar produto
5.  Relacionar usuário

------------------------------------------------------------------------

## Etapa 6 -- Telegram Bot

Implementar:

-   /start
-   /lista
-   /remover
-   /ajuda

Permitir cadastrar livros pelo link.

------------------------------------------------------------------------

## Etapa 7 -- Histórico de Preços

Registrar toda atualização em `price_history`.

------------------------------------------------------------------------

## Etapa 8 -- Atualização Manual

Criar um script:

``` bash
python update_products.py
```

Fluxo:

-   Buscar produtos
-   Agrupar em lotes de até 10 ASINs
-   Consultar PAAPI
-   Atualizar banco
-   Registrar histórico

------------------------------------------------------------------------

## Etapa 9 -- Detecção de Queda

Comparar preço anterior com o atual.

Se houve queda, gerar um evento interno.

------------------------------------------------------------------------

## Etapa 10 -- Notificações

Enviar mensagem aos usuários monitorando o produto.

Mensagem contendo:

-   Nome
-   Preço anterior
-   Novo preço
-   Economia
-   Link de afiliado

------------------------------------------------------------------------

## Etapa 11 -- Testes Locais

Validar:

-   vários usuários
-   produtos repetidos
-   atualização em lote
-   deduplicação (1 consulta → N notificações)

------------------------------------------------------------------------

## Etapa 12 -- Preparação para Produção

Separar configurações Local/Railway.

Adicionar:

-   logs
-   variáveis de ambiente
-   tratamento de exceções

------------------------------------------------------------------------

## Etapa 13 -- Deploy no Railway

Publicar:

-   aplicação
-   PostgreSQL
-   variáveis de ambiente

Manter atualização manual.

------------------------------------------------------------------------

## Etapa 14 -- Scheduler no Railway

Automatizar:

-   selecionar produtos
-   consultar PAAPI
-   atualizar preços
-   detectar quedas
-   enviar notificações

Inicialmente a cada 2 horas.

------------------------------------------------------------------------

## Etapa 15 -- Scheduler Inteligente

Atualizar frequência conforme quantidade de usuários monitorando cada
livro.

------------------------------------------------------------------------

## Etapa 16 -- Ferramentas Administrativas

Implementar:

-   /stats
-   /recheck
-   /broadcast
-   /logs

------------------------------------------------------------------------

## Etapa 17 -- Otimizações

-   Cache do token OAuth
-   Retry
-   Rate limiting
-   Cache local
-   Métricas
-   Tratamento de throttling

------------------------------------------------------------------------

# Diretrizes para o Agente de Código

Para cada etapa:

-   Desenvolver apenas a etapa atual.
-   Não antecipar funcionalidades futuras.
-   Escrever código modular.
-   Utilizar type hints.
-   Documentar classes e métodos.
-   Separar claramente API, banco, serviços e Telegram.
-   Ao final de cada etapa, explicar o que foi implementado e aguardar a
    próxima solicitação.
