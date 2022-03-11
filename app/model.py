import json
import uuid
from enum import Enum, IntEnum
from typing import List, Optional
from urllib import response

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound

from .db import engine

### User関連

class LiveDifficulty(Enum):
    normal = 1
    hard = 2

class JoinRoomResult(Enum):
    Ok = 1
    RoomFull = 2
    Disbanded = 3
    OtherError = 4

class WaitRoomStatus(Enum):
    Waiting = 1
    LiveStart = 2
    Dissolution = 3

class RoomUser(BaseModel):
    user_id: int
    name: str
    leader_card_id: int
    select_difficulty: LiveDifficulty
    is_me: bool
    is_host: bool

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

    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int

    class Config:
        orm_mode = True


def list_room(live_id: int) -> List:
    with engine.begin() as conn:
        response = conn.execute(
            text("SELECT * FROM room WHERE live_id=:live_id"),
            dict(live_id=live_id),
        )
    return response.all()


def join_room(
    room_id: int, select_difficulty: LiveDifficulty, user: SafeUser
) -> JoinRoomResult:
    with engine.begin() as conn:
        responses = conn.execute(
            text(
                "SELECT joined_user_count,max_user_count FROM room WHERE room_id=:room_id"
            ),
            dict(room_id=room_id),
        )
        response = responses.one()
        if response.joined_user_count >= response.max_user_count:
            return JoinRoomResult.RoomFull
        if response.joined_user_count == 0:
            return JoinRoomResult.Disbanded
        if response.joined_user_count < response.max_user_count:
            _ = conn.execute(
                text(
                    "INSERT INTO `room_member` SET `room_id`=:room_id, `user_id`=:user_id, `select_difficulty`=:select_difficulty, `is_me`=:is_me, `is_host`=:is_host, `judge_count_list`=:judge_count_list, `score`=:score"
                ),
                dict(
                    room_id=room_id,
                    user_id=user.id,
                    select_difficulty=select_difficulty.value,
                    is_me=1,
                    is_host=0,
                    judge_count_list=0,
                    score=0,
                ),
            )
            _ = conn.execute(
                text(
                    "UPDATE `room` SET `joined_user_count`=:joined_user_count WHERE `room_id`=room_id"
                ),
                dict(
                    joined_user_count=response.joined_user_count + 1,
                    room_id=room_id
                ),
            )

            return JoinRoomResult.Ok
    return JoinRoomResult.OtherError


## 戻り値が複数の時のアノテーション
def wait_room(room_id: int, user: SafeUser):
    with engine.begin() as conn:
        responses1 = conn.execute(
            text(
                "SELECT `user`.id, `user`.name, `user`.leader_card_id, `room_member`.select_difficulty, `room_member`.is_host FROM `room_member` INNER JOIN `room` ON `room`.room_id = `room_member`.room_id INNER JOIN `user` ON `room_member`.user_id = `user`.id WHERE `room`.room_id=:room_id"
            ),
            dict(room_id=room_id),
        )
        response1 = responses1.one()


