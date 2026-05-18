"""E2E 송신 테스트 — 시나리오 선택 → Claude 대화 생성 → Telethon 송신.

실행:
    docker compose exec -it backend python -m app.services.distribution.live_test \\
        --scenario "출고 알림 + 수량" \\
        [--bl <bl_record_id>] [--dry-run]

흐름:
1. 시나리오 + 발신/수신 페르소나 (role 매칭으로 자동 선택, 또는 명시).
2. BL (선택) 컨텍스트 로드.
3. Claude 로 대화 1세트 생성.
4. distribution_sessions + distribution_messages 저장 (status='approved' 자동).
5. 사용자에게 미리보기 + 확인.
6. Telethon 으로 sender → receiver 송신 (시간차 + 타이핑 시뮬레이션).
7. distribution_send_log + status 갱신.

--dry-run: 생성까지만 하고 실제 송신은 X. 미리보기만.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import random

from sqlalchemy import select
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact, User

from app.config import settings
from app.database import async_session
from app.models.distribution import (
    DistributionBlRecord,
    DistributionMessage,
    DistributionPersona,
    DistributionScenario,
    DistributionSendLog,
    DistributionSession,
)
from app.services.distribution.conversation_generator import (
    GenerationError,
    generate_conversation,
)
from app.services.distribution.encryption import decrypt
from app.services.distribution.scenario_engine import (
    BlContext,
    PersonaContext,
    ScenarioContext,
)

logger = logging.getLogger(__name__)


def _persona_to_context(persona: DistributionPersona) -> PersonaContext:
    return PersonaContext(
        account_label=persona.account_label,
        role=persona.role,
        display_name=persona.display_name,
        tone_profile=persona.tone_profile,
    )


def _scenario_to_context(scenario: DistributionScenario) -> ScenarioContext:
    return ScenarioContext(
        name=scenario.name,
        trigger_event=scenario.trigger_event,
        beats=scenario.beats or [],
        example_msgs=scenario.example_msgs,
        raw_text=scenario.raw_text,
    )


def _bl_to_context(bl: DistributionBlRecord | None) -> BlContext | None:
    if bl is None:
        return None
    return BlContext(
        bl_number=bl.bl_number,
        container_no=bl.container_no,
        product=bl.product,
        quantity=bl.quantity,
        departure_date=bl.departure_date,
        arrival_date=bl.arrival_date,
        destination=bl.destination,
    )


async def _resolve_peer(
    client: TelegramClient, target: DistributionPersona
) -> User:
    """sender 의 client 안에서 target 페르소나를 entity 로 해석.

    1. dialog 또는 contact 에 이미 있으면 ``get_entity`` 로 즉시 해석.
    2. 없으면 ``ImportContactsRequest`` 로 phone 등록 → 반환된 user 사용.
       이 경로는 수동 워밍업 없이도 양쪽이 서로 entity 를 알게 됨.

    주의:
    - target 의 텔레그램 프라이버시 설정에서 "Find me by phone" 이 막혀있으면
      ImportContactsRequest 결과의 ``imported`` 가 비어있을 수 있음.
      이 경우 retried 가 user 객체 반환 — fall back 처리.
    - 같은 phone 반복 import 는 텔레그램 측이 idempotent 처리 → 중복 contact 안 생김.
    """
    # 1차 시도: 이미 알고 있으면 즉시.
    try:
        return await client.get_entity(target.telegram_phone)
    except (ValueError, TypeError):
        pass

    # 2차 시도: phone 으로 contact import.
    contact = InputPhoneContact(
        client_id=random.randint(1, 2**31 - 1),
        phone=target.telegram_phone,
        first_name=target.display_name or target.account_label,
        last_name="",
    )
    result = await client(ImportContactsRequest([contact]))
    if result.users:
        return result.users[0]
    # 3차 fallback: get_entity 재시도 (contact 추가 후엔 캐시될 수 있음).
    try:
        return await client.get_entity(target.telegram_phone)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{target.account_label}({target.telegram_phone}) 를 contact 로 등록 못함. "
            "상대방 텔레그램 프라이버시 → '내 번호 찾기' 설정을 확인하거나, "
            "폰에서 수동으로 1번 메시지 보내주세요."
        ) from exc


async def _open_telethon_client(persona: DistributionPersona) -> TelegramClient:
    """이미 .session 으로 인증된 페르소나 → TelegramClient. 신규 로그인 X."""
    if not persona.session_path:
        raise RuntimeError(
            f"{persona.account_label}: 세션 파일 경로 없음. telethon_login 먼저 실행."
        )
    if not persona.api_id_enc or not persona.api_hash_enc:
        raise RuntimeError(f"{persona.account_label}: 자격증명 미설정.")
    api_id = int(decrypt(persona.api_id_enc))
    api_hash = decrypt(persona.api_hash_enc)
    client = TelegramClient(persona.session_path, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            f"{persona.account_label}: 세션 인증 안 됨. telethon_login 재실행 필요."
        )
    return client


async def run_test(
    *,
    scenario_name: str,
    bl_id: str | None = None,
    dry_run: bool = False,
) -> None:
    async with async_session() as db:
        # ---------------- 시나리오 ----------------
        scenario_q = await db.execute(
            select(DistributionScenario).where(
                DistributionScenario.name == scenario_name
            )
        )
        scenario = scenario_q.scalar_one_or_none()
        if scenario is None:
            raise ValueError(
                f"시나리오 '{scenario_name}' 없음. seeds 실행했는지 확인."
            )

        # ---------------- 페르소나 (role 매칭) ----------------
        sender_q = await db.execute(
            select(DistributionPersona)
            .where(DistributionPersona.role == scenario.sender_role)
            .where(DistributionPersona.active.is_(True))
            .limit(1)
        )
        sender = sender_q.scalar_one_or_none()
        receiver_q = await db.execute(
            select(DistributionPersona)
            .where(DistributionPersona.role == scenario.receiver_role)
            .where(DistributionPersona.active.is_(True))
            .limit(1)
        )
        receiver = receiver_q.scalar_one_or_none()
        if sender is None or receiver is None:
            raise ValueError(
                f"활성 페르소나 부족 — sender({scenario.sender_role}) "
                f"or receiver({scenario.receiver_role}). seeds + credential_loader."
            )
        if sender.id == receiver.id:
            raise ValueError("동일 페르소나가 sender/receiver 양쪽에 매칭됨.")

        # ---------------- BL (선택) ----------------
        bl = None
        if bl_id:
            bl_q = await db.execute(
                select(DistributionBlRecord).where(
                    DistributionBlRecord.id == UUID(bl_id)
                )
            )
            bl = bl_q.scalar_one_or_none()
            if bl is None:
                raise ValueError(f"BL {bl_id} 없음.")

        print(f"\n=== 테스트 시작 ===")
        print(f"시나리오: {scenario.name} ({scenario.trigger_event})")
        print(f"발신: {sender.account_label} → 수신: {receiver.account_label}")
        if bl:
            print(f"BL: {bl.bl_number or '(번호 없음)'} / {bl.product or ''}")
        print()

        # ---------------- Claude 생성 ----------------
        try:
            gen = generate_conversation(
                scenario=_scenario_to_context(scenario),
                sender=_persona_to_context(sender),
                receiver=_persona_to_context(receiver),
                bl=_bl_to_context(bl),
            )
        except GenerationError as exc:
            print(f"\n생성 실패: {exc}", file=sys.stderr)
            sys.exit(1)

        # ---------------- 미리보기 ----------------
        print("[생성된 대화 미리보기]")
        for idx, m in enumerate(gen.messages, start=1):
            print(
                f"  {idx:>2}. [{m.sender}] {m.content}  "
                f"(after {m.send_after_sec}s, typing {m.typing_sec}s)"
            )
        print(
            f"\n비용: ${gen.cost_usd:.5f} | "
            f"입력 {gen.input_tokens} tok | 출력 {gen.output_tokens} tok | "
            f"시도 {gen.attempts}회"
        )

        if dry_run:
            print("\n--dry-run: 송신 X. 종료.")
            return

        # ---------------- DB 저장 ----------------
        session_obj = DistributionSession(
            bl_record_id=bl.id if bl else None,
            scenario_id=scenario.id,
            sender_persona_id=sender.id,
            receiver_persona_id=receiver.id,
            status="approved",  # 테스트 모드 자동 승인.
            approved_at=datetime.now(timezone.utc),
            scheduled_start=datetime.now(timezone.utc),
            llm_cost_usd=gen.cost_usd,
            llm_input_tok=gen.input_tokens,
            llm_output_tok=gen.output_tokens,
        )
        db.add(session_obj)
        await db.flush()

        message_objs: list[tuple[DistributionMessage, str]] = []
        sender_by_label = {
            sender.account_label: sender,
            receiver.account_label: receiver,
        }
        for idx, m in enumerate(gen.messages):
            sender_for_msg = sender_by_label[m.sender]
            mobj = DistributionMessage(
                session_id=session_obj.id,
                order_index=idx,
                sender_persona_id=sender_for_msg.id,
                content=m.content,
                send_after_sec=m.send_after_sec,
                typing_sec=m.typing_sec,
                status="queued",
            )
            db.add(mobj)
            message_objs.append((mobj, m.sender))
        await db.commit()

        print(f"\n세션 저장 완료: {session_obj.id}")

        # ---------------- 사용자 확인 ----------------
        answer = input("\n위 내용으로 실제 송신하시겠습니까? [yes/N] ").strip().lower()
        if answer not in ("yes", "y"):
            print("취소됨. 세션은 DB 에 남아있음 (status=approved).")
            return

        # ---------------- Telethon 송신 ----------------
        print("\n=== 송신 시작 ===")
        clients: dict[str, TelegramClient] = {}
        # 각 발신 client 마다 상대 peer 를 미리 entity 로 해석해 캐시.
        # key = (from_label, to_label) → User
        peer_cache: dict[tuple[str, str], User] = {}
        try:
            for p in (sender, receiver):
                clients[p.account_label] = await _open_telethon_client(p)
                print(f"  {p.account_label}: 클라이언트 연결 OK")

            # 양방향 peer entity 사전 해석 (contact import 포함).
            for from_p, to_p in ((sender, receiver), (receiver, sender)):
                entity = await _resolve_peer(clients[from_p.account_label], to_p)
                peer_cache[(from_p.account_label, to_p.account_label)] = entity
                print(
                    f"  {from_p.account_label} → {to_p.account_label}: "
                    f"entity 해석 완료 (id={entity.id})"
                )

            # 송신은 발신자 client → 수신자 entity.
            for mobj, sender_label in message_objs:
                from_persona = sender_by_label[sender_label]
                to_persona = (
                    receiver if from_persona.id == sender.id else sender
                )
                target_entity = peer_cache[
                    (from_persona.account_label, to_persona.account_label)
                ]

                # 시간차 대기 (실시간 테스트 — 너무 길면 실용성 X. 30초 cap).
                wait_sec = min(mobj.send_after_sec, 30)
                if wait_sec > 0:
                    print(f"  ⏳ {wait_sec}초 대기...")
                    await asyncio.sleep(wait_sec)

                client = clients[from_persona.account_label]
                # 타이핑 인디케이터 — 짧게.
                async with client.action(target_entity, "typing"):
                    await asyncio.sleep(min(mobj.typing_sec, 5))

                try:
                    sent = await client.send_message(
                        target_entity,
                        mobj.edited_content or mobj.content,
                    )
                    mobj.status = "sent"
                    mobj.sent_at = datetime.now(timezone.utc)
                    mobj.telegram_message_id = str(sent.id)
                    db.add(mobj)
                    db.add(
                        DistributionSendLog(
                            message_id=mobj.id,
                            persona_id=from_persona.id,
                            attempt=1,
                            success=True,
                        )
                    )
                    print(
                        f"  ✅ [{from_persona.account_label}→{to_persona.account_label}] "
                        f"{mobj.content[:40]}..."
                    )
                except RPCError as exc:
                    mobj.status = "failed"
                    db.add(mobj)
                    db.add(
                        DistributionSendLog(
                            message_id=mobj.id,
                            persona_id=from_persona.id,
                            attempt=1,
                            success=False,
                            error_code=type(exc).__name__,
                            error_detail=str(exc),
                        )
                    )
                    print(f"  ❌ 송신 실패: {type(exc).__name__}: {exc}")
                await db.commit()
        finally:
            for c in clients.values():
                await c.disconnect()

        # 세션 완료 처리.
        session_obj.status = "sent"
        session_obj.completed_at = datetime.now(timezone.utc)
        db.add(session_obj)
        await db.commit()
        print(f"\n=== 송신 완료. 세션 {session_obj.id} status=sent ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="T9 E2E 송신 테스트")
    parser.add_argument(
        "--scenario", required=True, help="시나리오 이름 (예: '출고 알림 + 수량')"
    )
    parser.add_argument(
        "--bl", default=None, help="distribution_bl_records UUID (선택)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="생성만 하고 송신 X",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(
        run_test(
            scenario_name=args.scenario,
            bl_id=args.bl,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
