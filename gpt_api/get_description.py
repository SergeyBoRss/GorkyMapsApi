import time
import uuid
import json
import base64
import requests
from typing import List, Optional, Union, Dict, Any

from utils.config import GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET

GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


class GigaChatError(RuntimeError):
    pass


class _TokenCache:
    token: Optional[str] = None
    expires_at: float = 0.0


def _basic_auth(client_id: str, client_secret: str) -> str:
    b = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {b}"


def _get_access_token(verify: Union[bool, str]) -> str:
    if _TokenCache.token and time.time() < _TokenCache.expires_at:
        return _TokenCache.token

    client_id = GIGACHAT_CLIENT_ID
    client_secret = GIGACHAT_CLIENT_SECRET
    if not client_id or not client_secret:
        raise GigaChatError("GIGACHAT_CLIENT_ID / GIGACHAT_CLIENT_SECRET не заданы")

    headers = {
        "Authorization": _basic_auth(client_id, client_secret),
        "RqUID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"scope": "GIGACHAT_API_PERS"}
    r = requests.post(
        GIGACHAT_OAUTH_URL, headers=headers, data=data, verify=verify, timeout=15
    )
    if r.status_code != 200:
        raise GigaChatError(f"OAuth {r.status_code}: {r.text}")
    payload = r.json()
    token = payload.get("access_token")
    ttl = int(payload.get("expires_in", 1800))
    if not token:
        raise GigaChatError(f"No access_token: {payload}")
    _TokenCache.token = token
    _TokenCache.expires_at = time.time() + ttl - 30
    return token


def build_route_explanation(
    *,
    route_points: List[Dict[str, Any]],
    tags: List[str],
    time_limit_min: float,
    route_time_min: Optional[float] = None,
    criteria: str = "минимум времени при соблюдении интересов пользователя",
    model: str = "GigaChat-2",
    temperature: float = 0.3,
    max_tokens: int = 450,
    verify: Union[bool, str] = False,
    timeout: float = 30.0,
) -> str:
    compact = []
    for i, p in enumerate(route_points, 1):
        compact.append(
            {
                "order": i,
                "title": p.get("title") or "",
                "address": p.get("address") or "",
                "lat": (
                    round(float(p.get("latitude")), 6)
                    if p.get("latitude") is not None
                    else None
                ),
                "lon": (
                    round(float(p.get("longitude")), 6)
                    if p.get("longitude") is not None
                    else None
                ),
                "desc": (p.get("description") or ""),
            }
        )

    payload = {
        "criteria": criteria,
        "tags": tags,
        "time_limit_min": time_limit_min,
        "route_time_min": route_time_min,
        "route": compact,
    }

    user_prompt = f"""
Ты — экспертный гид по культурным маршрутам России.
Тебе передан готовый маршрут, который уже оптимизирован по времени и интересам пользователя.

---
**Данные маршрута (JSON):**
{json.dumps(payload, ensure_ascii=False, indent=2)}
---

Пожалуйста, сформулируй развёрнутое описание этого маршрута на хорошем русском языке.

Формат ответа:
1. **Соответствие времени:** оцени, укладывается ли маршрут во временной лимит (укажи лимит и примерную длительность маршрута в минутах).
2. **Соответствие интересам (теги):** теги перечислены на английском, но переведи их на русский (например ARCHITECTURE → архитектура, HISTORY → история). Покажи, как каждая точка маршрута соответствует указанным интересам. Используй более живое описание — что примечательно, чем уникальна архитектура/история.
3. **Описание точек:** для каждой остановки сделай 2–3 предложения, связывая их в плавный рассказ (например, "затем маршрут ведёт к...", "следующей остановкой становится...").
4. **Логика порядка точек:** объясни, почему именно такой порядок оптимален (по географии, смыслу или атмосфере).
5. **Итог:** короткий вывод — почему маршрут удачно сочетает время, интересы и логичную последовательность.

Пиши литературно, на русском языке, без маркированных HTML-тегов, максимум с лёгким Markdown для структуры.
"""

    access_token = _get_access_token(verify)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Ты — аккуратный и точный аналитик маршрутов.",
            },
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    r = requests.post(
        GIGACHAT_CHAT_URL, headers=headers, json=body, verify=verify, timeout=timeout
    )
    if r.status_code == 429:
        raise GigaChatError("HTTP 429: превышен лимит запросов GigaChat")
    if r.status_code >= 400:
        raise GigaChatError(f"GigaChat {r.status_code}: {r.text}")
    data = r.json()
    choices = data.get("choices") or []
    content = (
        choices[0]["message"]["content"].strip()
        if choices and "message" in choices[0]
        else ""
    )
    if not content:
        raise GigaChatError(f"Пустой ответ модели: {data}")
    return content
