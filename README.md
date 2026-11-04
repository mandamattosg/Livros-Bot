<p align="center">
  <img src="assets/logo.png" alt="Livros Bot" width="280">
</p>

# Livros Bot

Bot do Telegram que monitora preços de livros na Amazon Brasil e avisa quando o preço cai.

O usuário envia o link de um livro, o bot passa a acompanhar o preço pela **Amazon Creators API** e manda uma notificação quando houver uma queda relevante.

## Funcionalidades

- Cadastro de livros a partir de links da Amazon (inclusive links encurtados)
- Histórico de preços por produto
- Detecção de queda com valor mínimo absoluto **e** percentual configuráveis
- Notificações via Telegram com link de afiliado
- Frequência de atualização adaptativa: livros monitorados por mais usuários são atualizados com mais frequência
- Filas de monitoramento e de notificação com workers, retentativas, locks e recuperação de itens travados
- Tratamento de rate limit da Amazon (HTTP 429)
- Alertas e relatórios para o administrador (uso diário da API, atividade dos produtos, falhas)

## Comandos do bot

| Comando | Descrição |
|---|---|
| `/start` | Registra o usuário e mostra a ajuda |
| `/livro` | Pede o link de um livro para monitorar (também é possível só colar o link) |
| `/lista` | Lista os livros monitorados |
| `/status` | Mostra o preço atual de um livro |
| `/remover` | Remove um livro do monitoramento |
| `/ajuda` ou `/help` | Mostra a ajuda |
| `/relatorio` | Relatório geral (apenas administrador) |

## Arquitetura

```text
Telegram ──► Bot (app/bot) ──► ProductService ──► PostgreSQL
                                                     ▲
refresh_prices ──► fila de monitoramento ──► monitoring_worker ──► Amazon Creators API
                                                     │
                                       detecção de queda de preço
                                                     │
                   fila de notificação ──► notification_worker ──► Telegram
```

| Pasta | Conteúdo |
|---|---|
| `app/amazon` | Cliente da Creators API (OAuth, cache de token, registro de uso) |
| `app/bot` | Handlers do bot do Telegram |
| `app/models` | Modelos SQLAlchemy |
| `app/services` | Regras de negócio (produtos, preços, quedas, notificações, relatórios) |
| `app/scheduler` | Filas, workers e locks |
| `app/utils` | Parser de links, links de afiliado, datas em UTC |
| `tests` | Testes automatizados |

## Tecnologias

Python, python-telegram-bot, SQLAlchemy, PostgreSQL e Amazon Creators API.

## Licença

Todos os direitos reservados. O código está disponível apenas para consulta; não é permitido copiar, modificar, distribuir ou executar este projeto sem autorização prévia por escrito.
