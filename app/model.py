import json
from urllib import response
import uuid
from enum import Enum, IntEnum
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound

from .db import engine

### User関連

class InvalidToken(Exception):
    """指定されたtokenが不正だったときに投げる"""


class SafeUser(BaseModel):
    """token を含まないUser"""

    id: int
    name: str
    leader_card_id: int

    class Config:
        orm_mode = True


def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token"""
    token = str(uuid.uuid4())
    # NOTE: tokenが衝突したらリトライする必要がある.
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO `user` (name, token, leader_card_id) VALUES (:name, :token, :leader_card_id)"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
        # print(result)
    return token


def _get_user_by_token(conn, token: str) -> Optional[SafeUser]:
    result = conn.execute(
        text("SELECT * FROM `user` WHERE `token`=:token"), dict(token=token)
    ).one()
    return SafeUser.from_orm(result)


def get_user_by_token(token: str) -> Optional[SafeUser]:
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(token: str, name: str, leader_card_id: int) -> None:
    # このコードを実装してもらう
    with engine.begin() as conn:
        # TODO: 実装
        _ = conn.execute(
            text(
                "UPDATE `user` SET `name`=:name, `leader_card_id`=:leader_card_id WHERE `token`=:token"
            ),
            dict(name=name, token=token, leader_card_id=leader_card_id),
        )


### room関連のプログラム

def create_room(token: str, live_id: int, select_difficulty: int) -> int:
    with engine.begin() as conn:
        response = conn.execute(
            text(
                "INSERT INTO `room` SET `live_id`=:live_id, `joined_user_count`=:joined_user_count, `max_user_count`=:max_user_count"
            ),
            dict(live_id=live_id, joined_user_count=1, max_user_count=4),
        )
    return response.lastrowid

class RoomList(BaseModel):
    """token を含まないUser"""

    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int

    class Config:
        orm_mode = True


def list_room(live_id: str) -> List:
    with engine.begin() as conn:
        response = conn.execute(
            text(
                "SELECT * FROM room WHERE live_id=:live_id"
            ),
            dict(live_id=live_id),
        )
    return response.all()
    