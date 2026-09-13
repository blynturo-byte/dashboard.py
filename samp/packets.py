
import struct
import socket
import random
from functools import partial

from core.bitstream import BitStream
from .constants import (
    PacketID,
    RPC as RPCConstants
)
from logic.managers import PlayerInfo


from core.auth_keys import lookup_client_key


def gen_gpci(factor: int = 0x3e9) -> str:
    alphanum = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    out = [ord(random.choice(alphanum)) for _ in range(24)]

    if factor == 0:
        return "0"

    src = [0] * 5
    for i in range(5):
        word = (
            out[4 * i]
            | (out[4 * i + 1] << 8)
            | (out[4 * i + 2] << 16)
            | (out[4 * i + 3] << 24)
        )
        src[i] = (
            (word >> 24)
            | ((word << 8) & 0x00FF0000)
            | ((word >> 8) & 0x0000FF00)
            | (word << 24)
        ) & 0xFFFFFFFF

    result = 0
    for i in range(5):
        result += src[i] << (32 * i)
    result *= factor

    product_bytes = result.to_bytes(24, "little")
    product_bytes = product_bytes[::-1]

    notzero = 0
    chars = []
    for i in range(24):
        high = product_bytes[i] >> 4
        low = product_bytes[i] & 0x0F

        if notzero or high:
            chars.append(chr(high + 55) if high > 9 else chr(high + 48))
            notzero = 1

        if notzero or low:
            chars.append(chr(low + 55) if low > 9 else chr(low + 48))
            notzero = 1

    return "".join(chars) or "0"



class RPCBuilder:

    @staticmethod
    def _write_rpc_id(bs: BitStream, rpc_id: int) -> None:
        bs.write_bits(rpc_id & 0xFF, 8)

        bs.write_bits(0b11, 2)

    @staticmethod
    def create(
        rpc_id: int,
        payload: bytes = b"",
        payload_bitlen: int | None = None
    ) -> bytes:
        if payload is None:
            payload = b""

        if payload_bitlen is None:
            payload_bitlen = len(payload) * 8

        bs = BitStream()

        RPCBuilder._write_rpc_id(bs, rpc_id)

        bs.write_compressed(
            payload_bitlen,
            16,
            unsigned=True
        )

        if payload:
            bs.write_bytes(payload)

        return bs.get_bytes()

    @staticmethod
    def build(rpc_name: str, *args, **kwargs) -> bytes:
        try:
            rpc_id, payload_builder = RPC_BUILDERS[rpc_name]
        except KeyError:
            raise KeyError(f"unknown rpc builder: {rpc_name}") from None

        result = payload_builder(*args, **kwargs)

        if isinstance(result, tuple):
            payload, payload_bitlen = result
        else:
            payload = result
            payload_bitlen = len(payload or b"") * 8

        return RPCBuilder.create(
            rpc_id,
            payload,
            payload_bitlen
        )


    @staticmethod
    def payload_client_join(
        nickname: str,
        server_challenge: int,
    ) -> tuple[bytes, int]:
        IVERSION = 4057
        BYTE_MOD = 1
        CLIENT_VERSION = "0.3.7"

        nickname_bytes = nickname.encode("ascii", errors="ignore")
        auth_key = gen_gpci(0x3e9)
        auth_key_bytes = auth_key.encode("ascii", errors="ignore")
        client_version_bytes = CLIENT_VERSION.encode("ascii")

        ui_client_challenge_response = server_challenge ^ IVERSION

        bs = BitStream()

        bs.write_uint32(IVERSION)
        bs.write_uint8(BYTE_MOD)
        bs.write_uint8(len(nickname_bytes))
        bs.write_bytes(nickname_bytes)
        bs.write_uint32(ui_client_challenge_response)
        bs.write_uint8(len(auth_key_bytes))
        bs.write_bytes(auth_key_bytes)
        bs.write_uint8(len(client_version_bytes))
        bs.write_bytes(client_version_bytes)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_request_class(wclass: int = 0) -> tuple[bytes, int]:
        bs = BitStream()
        bs.write_uint32(wclass)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def spawn() -> tuple[bytes, int]:
        return b"", 0

    @staticmethod
    def payload_send_chat(message: str) -> tuple[bytes, int]:
        message_bytes = message.encode(
            "cp1251",
            errors="ignore"
        )

        if len(message_bytes) > 255:
            raise ValueError(
                f"chat message too long: {len(message_bytes)} bytes"
            )

        bs = BitStream()

        bs.write_uint8(len(message_bytes))
        bs.write_bytes(message_bytes)
        bs.write_uint8(0)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_server_command(command: str) -> tuple[bytes, int]:
        command_bytes = command.encode(
            "utf8",
            errors="ignore"
        )

        if len(command_bytes) == 0:
            return b"", 0

        bs = BitStream()

        bs.write_uint32(len(command_bytes))
        bs.write_bytes(command_bytes)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_update_scores_and_pings() -> tuple[bytes, int]:
        return b"", 0

    @staticmethod
    def payload_picked_up_pickup(pickup_id: int) -> tuple[bytes, int]:

        bs = BitStream()
        bs.write_int32(int(pickup_id))

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_death_notification(
        reason_death: int,
        killer_id: int = 65535,
    ) -> tuple[bytes, int]:

        bs = BitStream()
        bs.write_uint8(int(reason_death) & 0xFF)
        bs.write_uint16(int(killer_id) & 0xFFFF)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_enter_vehicle(
        vehicle_id: int,
        is_passenger: int = 0,
    ) -> tuple[bytes, int]:

        bs = BitStream()
        bs.write_uint16(int(vehicle_id) & 0xFFFF)
        bs.write_uint8(int(is_passenger) & 0xFF)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_exit_vehicle(vehicle_id: int) -> tuple[bytes, int]:

        bs = BitStream()
        bs.write_uint16(int(vehicle_id) & 0xFFFF)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_select_text_draw(textdraw_id: int) -> tuple[bytes, int]:
        bs = BitStream()
        bs.write_uint16(int(textdraw_id) & 0xFFFF)

        return bs.get_bytes(), len(bs)

    @staticmethod
    def payload_dialog_response(
        dialog_id: int,
        response: int,
        list_item: int,
        text: str,
    ) -> tuple[bytes, int]:

        text_bytes = text.encode("cp1251", errors="ignore")

        bs = BitStream()
        bs.write_int16(int(dialog_id) & 0xFFFF)
        bs.write_uint8(int(response) & 0xFF)
        bs.write_uint16(int(list_item) & 0xFFFF)
        bs.write_uint8(len(text_bytes) & 0xFF)
        bs.write_bytes(text_bytes)

        return bs.get_bytes(), len(bs)


RPC_BUILDERS = {
    "client_join": (
        RPCConstants.CLIENT_JOIN,
        RPCBuilder.payload_client_join,
    ),

    "request_class": (
        RPCConstants.REQUEST_CLASS,
        RPCBuilder.payload_request_class,
    ),

    "spawn": (
        RPCConstants.SPAWN,
        RPCBuilder.spawn,
    ),

    "send_chat": (
        RPCConstants.CHAT,
        RPCBuilder.payload_send_chat,
    ),

    "server_command": (
        RPCConstants.SERVER_COMMAND,
        RPCBuilder.payload_server_command,
    ),

    "update_scores_and_pings": (
        RPCConstants.UPDATE_SCORES_PINGS_IPS,
        RPCBuilder.payload_update_scores_and_pings,
    ),

    "picked_up_pickup": (
        RPCConstants.PICKED_UP_PICKUP,
        RPCBuilder.payload_picked_up_pickup,
    ),

    "death_notification": (
        RPCConstants.DEATH,
        RPCBuilder.payload_death_notification,
    ),

    "enter_vehicle": (
        RPCConstants.ENTER_VEHICLE,
        RPCBuilder.payload_enter_vehicle,
    ),

    "exit_vehicle": (
        RPCConstants.EXIT_VEHICLE,
        RPCBuilder.payload_exit_vehicle,
    ),
    "dialog_response": (
        RPCConstants.DIALOG_RESPONSE,
        RPCBuilder.payload_dialog_response,
    ),
    "select_text_draw": (
        RPCConstants.SELECT_TEXT_DRAW,
        RPCBuilder.payload_select_text_draw,
    ),
}


class SyncPayloadBuilder:

    @staticmethod
    def player_sync(player: PlayerInfo) -> bytes:
        bs = BitStream()

        bs.write_uint16(player.lr)
        bs.write_uint16(player.ud)
        bs.write_uint16(player.keys)

        bs.write_float(player.x)
        bs.write_float(player.y)
        bs.write_float(player.z)

        bs.write_float(player.quat_w)
        bs.write_float(player.quat_x)
        bs.write_float(player.quat_y)
        bs.write_float(player.quat_z)

        bs.write_uint8(int(player.health))
        bs.write_uint8(int(player.armour))

        bs.write_bits(player.additional_key & 0x03, 2)
        bs.write_bits(player.weapon_id & 0x3F, 6)

        bs.write_uint8(player.special_action)

        bs.write_float(player.velocity_x)
        bs.write_float(player.velocity_y)
        bs.write_float(player.velocity_z)

        bs.write_float(player.surfing_x)
        bs.write_float(player.surfing_y)
        bs.write_float(player.surfing_z)

        bs.write_uint16(player.surfing_vehicle_id)

        bs.write_int16(player.animation_id)
        bs.write_int16(player.animation_flags)

        return bs.get_bytes()

    @staticmethod
    def vehicle_sync(player: PlayerInfo) -> bytes:
        bs = BitStream()

        bs.write_uint16(player.vehicle_id)

        bs.write_uint16(player.lr)
        bs.write_uint16(player.ud)
        bs.write_uint16(player.keys)

        bs.write_float(player.quat_w)
        bs.write_float(player.quat_x)
        bs.write_float(player.quat_y)
        bs.write_float(player.quat_z)

        bs.write_float(player.x)
        bs.write_float(player.y)
        bs.write_float(player.z)

        bs.write_float(player.velocity_x)
        bs.write_float(player.velocity_y)
        bs.write_float(player.velocity_z)

        bs.write_float(player.vehicle_health)

        bs.write_uint8(int(float(player.health)))
        bs.write_uint8(int(float(player.armour)))

        bs.write_bits(player.additional_key & 0x03, 2)
        bs.write_bits(player.weapon_id & 0x3F, 6)

        bs.write_uint8(player.siren_state)
        bs.write_uint8(player.landing_gear_state)

        bs.write_uint16(player.trailer_id)
        bs.write_float(player.train_speed)

        bs.write_uint16(player.extra)

        return bs.get_bytes()

    @staticmethod
    def passenger_sync(player: PlayerInfo) -> bytes:
        bs = BitStream()

        bs.write_uint16(player.vehicle_id)

        drive_by = 0
        seat_id = int(getattr(player, "current_vehicle_seat_id", 0)) & 0x3F
        additional_key = player.additional_key & 0x03
        weapon_id = player.weapon_id & 0x3F

        bs.write_bits(drive_by, 2)
        bs.write_bits(seat_id, 6)
        bs.write_bits(additional_key, 2)
        bs.write_bits(weapon_id, 6)

        bs.write_uint8(int(player.health))
        bs.write_uint8(int(player.armour))

        bs.write_uint16(player.lr)
        bs.write_uint16(player.ud)
        bs.write_uint16(player.keys)

        bs.write_float(player.x)
        bs.write_float(player.y)
        bs.write_float(player.z)

        return bs.get_bytes()


class PacketPayloadBuilder:

    @staticmethod
    def open_connection_request(cookie: int = 0x6969) -> bytes:
        cookie ^= 0x6969
        return bytes([(cookie >> 8) & 0xFF, cookie & 0xFF])

    @staticmethod
    def connection_request(password: str | None = None) -> bytes:
        if not password:
            return b""

        password_bytes = str(password).encode("ascii", errors="ignore")

        return password_bytes

    @staticmethod
    def auth_key_response(server_key: str) -> bytes:
        client_key = lookup_client_key(server_key)

        if client_key is None:
            raise ValueError(
                "The server uses a new SA-MP version that PyRakSAMP "
                "does not support."
            )

        client_key_bytes = client_key.encode("ascii")

        return (
            bytes([len(client_key_bytes)]) +
            client_key_bytes

        )

    @staticmethod
    def new_incoming_connection(server_ip: str, server_port: int) -> bytes:
        ip_bytes = socket.inet_aton(server_ip)
        port_bytes = struct.pack(">H", server_port)

        return (
            ip_bytes +
            port_bytes 

        )

    @staticmethod
    def internal_ping(session_ms: int) -> bytes:
        return struct.pack("<I", session_ms)

    @staticmethod
    def connected_pong(receiver_ms: int, sender_ms: int) -> bytes:
        return (
            struct.pack("<I", sender_ms) +
            struct.pack("<I", receiver_ms)
        )

    @staticmethod
    def received_static_data() -> bytes:
        return b""

    @staticmethod
    def detect_lost_connections() -> bytes:
        return b""

    @staticmethod
    def disconnection_notification() -> bytes:
        return b""


PACKET_REGISTRY: dict[str, tuple[int, "Callable[..., bytes]"]] = {
    "open_connection_request": (
        PacketID.OPEN_CONNECTION_REQUEST,
        PacketPayloadBuilder.open_connection_request,
    ),
    "connection_request": (
        PacketID.CONNECTION_REQUEST,
        PacketPayloadBuilder.connection_request,
    ),
    "auth_key_response": (
        PacketID.AUTH_KEY_RESPONSE,
        PacketPayloadBuilder.auth_key_response,
    ),
    "new_incoming_connection": (
        PacketID.NEW_INCOMING_CONNECTION,
        PacketPayloadBuilder.new_incoming_connection,
    ),
    "internal_ping": (
        PacketID.INTERNAL_PING,
        PacketPayloadBuilder.internal_ping,
    ),
    "connected_pong": (
        PacketID.CONNECTED_PONG,
        PacketPayloadBuilder.connected_pong,
    ),
    "received_static_data": (
        PacketID.RECEIVED_STATIC_DATA,
        PacketPayloadBuilder.received_static_data,
    ),
    "detect_lost_connections": (
        PacketID.DETECT_LOST_CONNECTIONS,
        PacketPayloadBuilder.detect_lost_connections,
    ),
    "disconnection_notification": (
        PacketID.DISCONNECTION_NOTIFICATION,
        PacketPayloadBuilder.disconnection_notification,
    ),
    "player_sync": (
        PacketID.PLAYER_SYNC,
        SyncPayloadBuilder.player_sync,
    ),
    "vehicle_sync": (
        PacketID.VEHICLE_SYNC,
        SyncPayloadBuilder.vehicle_sync,
    ),
    "passenger_sync": (
        PacketID.PASSENGER_SYNC,
        SyncPayloadBuilder.passenger_sync,
    ),
}


class PacketBuilder:

    @staticmethod
    def create(packet_id: int, payload: bytes = b"") -> bytes:
        if payload is None:
            payload = b""

        return bytes([packet_id & 0xFF]) + payload

    @staticmethod
    def build(name: str, *args, **kwargs) -> bytes:
        try:
            packet_id, payload_builder = PACKET_REGISTRY[name]
        except KeyError:
            raise KeyError(f"unknown packet payload builder: {name}") from None

        payload = payload_builder(*args, **kwargs)

        return PacketBuilder.create(packet_id, payload)

    @staticmethod
    def rpc(rpc_body: bytes) -> bytes:
        return PacketBuilder.create(
            PacketID.RPC,
            rpc_body
        )

    @staticmethod
    def rpc_build(rpc_name: str, *args, **kwargs) -> bytes:
        return PacketBuilder.rpc(
            RPCBuilder.build(rpc_name, *args, **kwargs)
        )




for _name in PACKET_REGISTRY:
    if not hasattr(PacketBuilder, _name):
        setattr(
            PacketBuilder,
            _name,
            staticmethod(partial(PacketBuilder.build, _name))
        )

for _rpc_name in RPC_BUILDERS:
    _wrapper_name = f"rpc_{_rpc_name}"
    if not hasattr(PacketBuilder, _wrapper_name):
        setattr(
            PacketBuilder,
            _wrapper_name,
            staticmethod(partial(PacketBuilder.rpc_build, _rpc_name))
        )
