# KVYT

Система бронювання квитків на події: концерти, стендапи, фестивалі.
Покупець дивиться афішу, обирає сеанс і місця в залі, тримає їх за собою
10 хвилин і підтверджує бронь.

Система складається з кількох сервісів і бази даних, усе запускається
в Docker однією командою. Знадвору доступні дві адреси:

- **`http://localhost:3000`** — сайт для покупців;
- **`http://localhost:8080`** — API, яким користується сайт і з яким можна працювати напряму.

## Вимоги

- **Docker Desktop** (з ним іде `docker compose`). Python, залежності й база
  живуть у контейнерах, окремо нічого ставити не треба.
- **Вільні порти 3000 і 8080.**
- **Близько 2 ГБ** на диску під образи й базу.

## Запуск

```bash
make up
```

Команда збере образи, підніме систему, дочекається, доки всі сервіси
стануть healthy, завантажить стартові дані й надрукує:

```
Web:     http://localhost:3000
Gateway: http://localhost:8080
```

Відкрийте `http://localhost:3000` у браузері — це сайт, на якому покупці
обирають подію, сеанс і місця.

Перший запуск довший — Docker качає базові образи й збирає контейнери.

### Конкретний стан системи

Якщо вам дали номер уроку, підніміть систему саме в тому стані, який для нього потрібен:

```bash
git pull
make lesson 3.2
```

Команда підніме систему в тій версії коду, з якою вийшов цей стан (код у вашій
папці при цьому не змінюється). Тому спершу `git pull`: без нього нової версії
локально немає, і команда попередить, що бере поточний код.
Повернутись до звичайного стану — `make up`. Який стан зараз активний,
показує `make doctor` у рядку `BUG_SCENARIO`.

### Налаштування

Налаштування лежать у файлі `.env`. Якщо його немає, `make up` створить його
з `.env.example` сам; можна й вручну: `cp .env.example .env`.

## Перевірка

```bash
curl http://localhost:8080/health/ready
```

Відповідь `200` з `"status":"ok"` означає, що система готова приймати запити:

```json
{"service":"gateway","status":"ok","deps":{"identity":"ok","catalog":"ok","booking":"ok"}}
```

Якщо щось лежить — буде `503`, а в `deps` видно, що саме.

Стан усіх контейнерів:

```bash
docker compose ps
```

Усі мають бути `healthy`. Контейнер `seed` — виняток: він завантажує стартові
дані й завершується, для нього нормальний стан — `Exited (0)`.

## Тестові облікові записи

Пароль у всіх однаковий: `Passw0rd!`

| Email                   | Роль        |
|-------------------------|-------------|
| `admin@kvyt.local`      | `admin`     |
| `organizer@kvyt.local`  | `organizer` |
| `organizer2@kvyt.local` | `organizer` |
| `anna@kvyt.local`       | `user`      |
| `borys@kvyt.local`      | `user`      |

Новий покупець реєструється сам через `POST /api/v1/auth/register` і отримує роль `user`.
Роль змінює адміністратор (`PATCH /api/v1/users/{user_id}`); нова роль діє з наступного
токена. Хто що може — в описі кожного ендпоінта в `http://localhost:8080/docs`.

Невдалі входи обмежені: після 5 невдалих спроб за 60 секунд для одного email
вхід повертає `429` із заголовком `Retry-After`. Успішний вхід обнуляє лічильник.

## Перші запити

Усі шляхи API починаються з `/api/v1`.

Опис API — `http://localhost:8080/docs` (Swagger UI, кнопка **Authorize** для токена).
Сама специфікація OpenAPI — `http://localhost:8080/openapi.json`, у репозиторії —
`services/gateway/openapi.yaml`.

Афіша доступна без входу:

```bash
curl http://localhost:8080/api/v1/events
```

Вхід повертає `access_token` (живе 15 хвилин) і `refresh_token`:

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"anna@kvyt.local","password":"Passw0rd!"}'
```

Далі токен передається в заголовку:

```bash
curl http://localhost:8080/api/v1/me \
  -H 'Authorization: Bearer <access_token>'
```

Кожна відповідь має заголовок `X-Trace-Id`. Якщо щось пішло не так — цей
ідентифікатор варто зберегти: за ним запит знаходиться в логах
(`docker compose logs | grep <trace_id>`). Можна передати свій `X-Trace-Id`
у запиті, і система використає його.

Помилки мають однаковий формат:

```json
{"error": {"code": "seat_already_held", "message": "Seat 2 in row B is on hold", "trace_id": "..."}}
```

`code` стабільний, на нього можна спиратись у перевірках; `message` — для людини.

## Партнери (OAuth2)

Сторонні застосунки отримують токен через OAuth2, а не через `/auth/login`.
Зареєстровано два клієнти:

| Клієнт | Хто це | Флоу | Секрет | Scopes |
|---|---|---|---|---|
| `partner-app` | застосунок-календар, діє від імені людини | Authorization Code + PKCE (`S256`, обовʼязково) | немає (public) | `profile:read`, `bookings:read`, `bookings:write` |
| `partner-service` | сервіс партнера, діє від свого імені | Client Credentials | `PARTNER_SERVICE_SECRET` з `.env`, за замовчуванням `partner-secret-local-only` | `occupancy:read` |

Адреси:

- Auth URL: `http://localhost:8080/oauth/authorize`
- Access Token URL: `http://localhost:8080/oauth/token`

Дозволені `redirect_uri` для `partner-app` (збіг має бути точним):
`https://oauth.pstmn.io/v1/callback`, `https://oauth.pstmn.io/v1/browser-callback`,
`http://localhost:3000/oauth/callback` (сторінка показує `code` і `state` — для обміну вручну).

Токен живе 15 хвилин, `refresh_token` в OAuth немає. Токен із scopes відкриває тільки
те, що дозволяють scopes: `profile:read` — `GET /api/v1/me`, `bookings:read` — перегляд
своїх броней, `bookings:write` — створення, підтвердження, скасування й видалення броней,
`occupancy:read` — `GET /api/v1/partner/occupancy`. Усе інше з токеном OAuth дає `403`
(`insufficient_scope`). Права ролі scopes не розширюють.

### Токен у Postman

Вкладка **Authorization** → Type **OAuth 2.0** → **Configure New Token**.

`partner-app`, від імені людини:

- Grant type: **Authorization Code (With PKCE)**, Code Challenge Method: **SHA-256**
- Callback URL: `https://oauth.pstmn.io/v1/callback` (або позначка **Authorize using browser**)
- Auth URL і Access Token URL — як вище
- Client ID: `partner-app`, Client Secret — порожньо
- Scope: наприклад `bookings:read`
- Client Authentication: **Send client credentials in body**

**Get New Access Token** відкриває сторінку KVYT: увійдіть як `anna@kvyt.local` / `Passw0rd!`
і натисніть **Allow**.

З позначкою **Authorize using browser** сторінка відкривається в браузері, а код повертається
в Postman через спливне вікно `oauth.pstmn.io`. Якщо браузер показує «Your call is
authenticated», а Postman далі чекає, дозвольте спливні вікна для `oauth.pstmn.io` і повторіть.
Postman чекає відповіді з браузера обмежений час: натискайте **Allow** одразу.

`partner-service`, без людини:

- Grant type: **Client Credentials**
- Access Token URL — як вище
- Client ID: `partner-service`, Client Secret: значення `PARTNER_SERVICE_SECRET`
- Scope: `occupancy:read`
- Client Authentication: будь-який варіант (Basic Auth header або в body)

З цим токеном: `GET http://localhost:8080/api/v1/partner/occupancy?session_id=<id сеансу>`.

## Зупинка

```bash
make down
```

Зупиняє контейнери, дані лишає — наступний `make up` підніме систему з тим
самим станом.

## Якщо щось пішло не так

### Спершу — діагностика

```bash
make doctor
```

Перевіряє Docker, порт 8080, кожен контейнер, готовність кожного сервісу,
звʼязки між ними і чи завантажені стартові дані. Кожен рядок — `OK` або
`FAIL`, і під кожним `FAIL` написано, що робити. Виправляйте з першого `FAIL`:
наступні часто є його наслідком.

### Повернутись у чистий стан

```bash
make reset
```

Зупиняє контейнери, **видаляє базу разом з усіма даними**, піднімає систему
заново й завантажує стартові дані. Після `make reset` система завжди в одному
й тому самому стані: ті самі події, місця й користувачі з тими самими id,
жодної броні.

Це правильний крок, коли дані зіпсовані або незрозуміло, що з ними відбувалось.

### Якщо порт зайнятий

`make up` падає з помилкою на кшталт `port is already allocated`, а
`make doctor` показує, хто тримає порт 3000 чи 8080. Те саме вручну:

```bash
lsof -i :8080
lsof -i :3000
```

У виводі буде `COMMAND` і `PID` процесу. Далі два варіанти.

Якщо це щось ваше і його не шкода зупинити:

```bash
kill <PID>
```

Якщо процес не реагує — `kill -9 <PID>`. Перед тим, як убивати, подивіться на
`COMMAND`: якщо це не ваш dev-сервер, а щось системне, краще не чіпати.

Якщо це старі контейнери KVYT — зупиніть їх нормальним способом:

```bash
make down
```

Другий варіант — лишити чужий процес у спокої і віддати KVYT інший порт.
Тоді в `docker-compose.yml` у потрібному сервісі (`gateway` для 8080, `web`
для 3000) змініть ліву частину:

```yaml
    ports:
      - "8081:8000"
```

і відкривайте систему на новому порту. Права частина (`8000`) — це порт
усередині контейнера, її чіпати не треба.

### Docker не запущений

`make up` або `make doctor` пише `Cannot connect to the Docker daemon`.
Запустіть Docker Desktop і дочекайтесь, доки він покаже, що рушій працює,
потім повторіть команду.
