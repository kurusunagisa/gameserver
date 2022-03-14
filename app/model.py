import json
import uuid
from email.policy import HTTP
from enum import Enum, IntEnum
from os import stat
from typing import List, Optional
from urllib import response

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import false, text, true
from sqlalchemy.exc import NoResultFound, MultipleResultsFound

from .db import engine

# User関連


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
    with engine.begin() as conn:
        # トークンが既存のものと衝突しなくなるまでトークンを生成する
        while True:
            token = str(uuid.uuid4())
            result = conn.execute(
                text("SELECT * FROM `user` WHERE `user`.token=:token"),
                {"token": token},
            ).first()
            if result == None:
                break

        _ = conn.execute(
            text(
                "INSERT INTO `user` (name, token, leader_card_id) VALUES (:name, :token, :leader_card_id)"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
    return token


def _get_user_by_token(conn, token: str) -> Optional[SafeUser]:
    try:
        result = conn.execute(
            text("SELECT * FROM `user` WHERE `token`=:token"), dict(token=token)
        ).one()
    except NoResultFound:
        raise HTTPException(status_code=404)
    except MultipleResultsFound:
        raise HTTPException(status_code=500)
    return SafeUser.from_orm(result)


def get_user_by_token(token: str) -> Optional[SafeUser]:
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(token: str, name: str, leader_card_id: int) -> None:
    with engine.begin() as conn:
        _ = conn.execute(
            text(
                "UPDATE `user` SET `name`=:name, `leader_card_id`=:leader_card_id WHERE `token`=:token"
            ),
            dict(name=name, token=token, leader_card_id=leader_card_id),
        )


# room関連のプログラム


def create_room(token: str, live_id: int, select_difficulty: int) -> int:
    with engine.begin() as conn:
        response = conn.execute(
            text(
                "INSERT INTO `room` SET `live_id`=:live_id, `joined_user_count`=:joined_user_count, `max_user_count`=:max_user_count, `is_start`=:is_start"
            ),
            dict(live_id=live_id, joined_user_count=1, max_user_count=4, is_start=1),
        )
        user = get_user_by_token(token)
        _ = conn.execute(
            text(
                "INSERT INTO `room_member` SET `room_id`=:room_id, `user_id`=:user_id, `select_difficulty`=:select_difficulty, `is_host`=:is_host, `judge_miss`=:judge_miss, `judge_bad`=:judge_bad, `judge_good`=:judge_good, `judge_great`=:judge_great, `judge_perfect`=:judge_perfect, `score`=:score"
            ),
            dict(
                room_id=response.lastrowid,
                user_id=user.id,
                select_difficulty=select_difficulty.value,
                is_host=True,
                judge_miss=0,
                judge_bad=0,
                judge_good=0,
                judge_great=0,
                judge_perfect=0,
                score=0,
            ),
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
        if live_id == 0:
            # live_idが0のときは入室できる全てのライブを取得する
            response = conn.execute(
                text("SELECT * FROM `room` WHERE `is_start`=:is_start"),
                dict(is_start=WaitRoomStatus.Waiting.value),
            )
        else:
            # 指定したライブIDでかつ入室できるライブを取得する
            response = conn.execute(
                text(
                    "SELECT * FROM `room` WHERE live_id=:live_id AND `is_start`=:is_start"
                ),
                dict(live_id=live_id, is_start=WaitRoomStatus.Waiting.value),
            )
    return response.all()


def join_room(
    room_id: int, select_difficulty: LiveDifficulty, user: SafeUser
) -> JoinRoomResult:
    with engine.begin() as conn:
        try:
            response = conn.execute(
                text(
                    "SELECT `joined_user_count`, `max_user_count`, `is_start` FROM `room` WHERE `room_id`=:room_id FOR UPDATE"
                ),
                dict(room_id=room_id),
            ).one()
        except NoResultFound:
            raise HTTPException(status_code=404)
        except MultipleResultsFound:
            raise HTTPException(status_code=500)

        if response.is_start != WaitRoomStatus.Waiting.value:
            return JoinRoomResult.Disbanded
        if response.joined_user_count >= response.max_user_count:
            return JoinRoomResult.RoomFull
        if response.joined_user_count == 0:
            return JoinRoomResult.Disbanded
        if response.joined_user_count < response.max_user_count:
            _ = conn.execute(
                text(
                    "INSERT INTO `room_member` SET `room_id`=:room_id, `user_id`=:user_id, `select_difficulty`=:select_difficulty, `is_host`=:is_host, `judge_miss`=:judge_miss, `judge_bad`=:judge_bad, `judge_good`=:judge_good, `judge_great`=:judge_great, `judge_perfect`=:judge_perfect, `score`=:score"
                ),
                dict(
                    room_id=room_id,
                    user_id=user.id,
                    select_difficulty=select_difficulty.value,
                    is_host=False,
                    judge_miss=0,
                    judge_bad=0,
                    judge_good=0,
                    judge_great=0,
                    judge_perfect=0,
                    score=0,
                ),
            )
            _ = conn.execute(
                text(
                    "UPDATE `room` SET `joined_user_count`=:joined_user_count WHERE `room_id`=room_id"
                ),
                dict(joined_user_count=response.joined_user_count + 1, room_id=room_id),
            )

            return JoinRoomResult.Ok
    return JoinRoomResult.OtherError


# 戻り値が複数の時のアノテーション
def wait_room(room_id: int, user: SafeUser):
    with engine.begin() as conn:
        response = conn.execute(
            text("SELECT `is_start` FROM `room` where `room_id`=:room_id"),
            dict(room_id=room_id),
        )
        result = conn.execute(
            text(
                "SELECT `room_member`.user_id, `user`.name, `user`.leader_card_id, `room_member`.select_difficulty, `room_member`.is_host FROM `room_member` INNER JOIN `room` ON `room`.room_id = `room_member`.room_id INNER JOIN `user` ON `room_member`.user_id = `user`.id WHERE `room`.room_id=:room_id"
            ),
            dict(room_id=room_id),
        ).all()
        resultList = []
        for r in result:
            resultList.append(
                RoomUser(
                    user_id=r.user_id,
                    name=r.name,
                    leader_card_id=r.leader_card_id,
                    select_difficulty=r.select_difficulty,
                    is_me=user.id == r.user_id,
                    is_host=r.is_host,
                )
            )
        try:
            is_start = response.one().is_start
        except (NoResultFound, MultipleResultsFound):
            raise HTTPException(status_code=500)
        return is_start, resultList


def start_room(room_id: int, user: SafeUser) -> None:
    with engine.begin() as conn:
        try:
            response = conn.execute(
                text(
                    "SELECT `is_host` FROM `room_member` WHERE `room_id`=:room_id AND `user_id`=:user_id"
                ),
                dict(room_id=room_id, user_id=user.id),
            )
            r = response.one()[0]
        except (NoResultFound, MultipleResultsFound):
            raise HTTPException(status_code=500)
        if r:
            _ = conn.execute(
                text("UPDATE `room` SET `is_start`=:is_start WHERE `room_id`=:room_id"),
                dict(is_start=WaitRoomStatus.LiveStart.value, room_id=room_id),
            )
        else:
            raise HTTPException(status_code=403)


def end_room(
    room_id: int, score: int, user: SafeUser, judge_count_list: list[int]
) -> None:
    while len(judge_count_list) < 5:
        judge_count_list.append(0)
    with engine.begin() as conn:
        _ = conn.execute(
            text(
                "UPDATE `room_member` SET `judge_perfect`=:judge_perfect, `judge_great`=:judge_great, `judge_good`=:judge_good, `judge_bad`=:judge_bad, `judge_miss`=:judge_miss, `score`=:score WHERE `user_id`=:user_id AND `room_id`=:room_id"
            ),
            dict(
                judge_perfect=judge_count_list[0],
                judge_great=judge_count_list[1],
                judge_good=judge_count_list[2],
                judge_bad=judge_count_list[3],
                judge_miss=judge_count_list[4],
                score=score,
                user_id=user.id,
                room_id=room_id,
            ),
        )


class ResultUser(BaseModel):
    user_id: int
    judge_count_list: list[int]
    score: int


def result_room(room_id: int) -> list[ResultUser]:
    with engine.begin() as conn:
        try:
            result = conn.execute(
                text(
                    "SELECT `user_id`, `judge_perfect`, `judge_great`, `judge_good`, `judge_bad`, `judge_miss`, `score` FROM `room_member` WHERE `room_id`=:room_id"
                ),
                dict(room_id=room_id),
            )
            resultList = []
            result2 = conn.execute(
                text("SELECT `is_start` FROM `room` WHERE `room_id`=:room_id"),
                dict(room_id=room_id),
            )
            is_start = result2.one()[0]
        except (NoResultFound, MultipleResultsFound):
            raise HTTPException(status_code=500)
        if is_start != WaitRoomStatus.Waiting.value:
            for i in result.all():
                resultList.append(
                    ResultUser(
                        user_id=i.user_id, judge_count_list=list(i[1:6]), score=i.score
                    )
                )
    return resultList


def leave_room(room_id: int, user: SafeUser) -> None:
    with engine.begin() as conn:
        try:
            # ホストか確認
            response = conn.execute(
                text(
                    "SELECT `is_host` FROM `room_member` WHERE `room_id`=:room_id AND `user_id`=:user_id"
                ),
                dict(room_id=room_id, user_id=user.id),
            )
            is_host = response.one()[0]
        except (NoResultFound, MultipleResultsFound):
            raise HTTPException(status_code=500)
        if is_host:
            # 他にメンバーがいるか確認
            result = conn.execute(
                text("SELECT `user_id` FROM `room_member` WHERE `room_id`=:room_id"),
                dict(room_id=room_id),
            )
            for i in result.all():
                # 他にメンバーがいる時
                if i[0] != user.id:
                    _ = conn.execute(
                        text(
                            "UPDATE `room_member` SET `is_host`=:is_host WHERE `user_id`=:user_id AND `room_id`=:room_id"
                        ),
                        dict(is_host=True, user_id=i[0], room_id=room_id),
                    )
                    _ = conn.execute(
                        text(
                            "DELETE FROM `room_member` WHERE `user_id`=:user_id AND `room_id`=:room_id"
                        ),
                        dict(user_id=user.id, room_id=room_id),
                    )
                    return
            # 他にメンバーがいない時
            # ルームを解散する
            _ = conn.execute(
                text(
                    "UPDATE `room` SET `is_start`=:is_start, `joined_user_count`=:joined_user_count WHERE `room_id`=:room_id"
                ),
                dict(
                    is_start=WaitRoomStatus.Dissolution.value,
                    joined_user_count=0,
                    room_id=room_id,
                ),
            )
            # 部屋をデータベースから消す
            _ = conn.execute(
                text("DELETE FROM `room` WHERE `room_id`=:room_id"),
                dict(room_id=room_id),
            )
