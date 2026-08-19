import math

from core.bitstream import BitStream
from core import logger
from .constants import (
    PacketID,
    RPC as RPCConstants
)



class RPCParser:

    @staticmethod
    def server_quit(bs: BitStream) -> dict | None:

        player_id = bs.read_uint16()
        reason = bs.read_uint8()

        return {
            "player_id": player_id,
            "reason": reason
        }

    @staticmethod
    def server_join(bs: BitStream) -> dict | None:

        player_id = bs.read_uint16()
        color = bs.read_uint32()
        is_npc = bs.read_uint8()

        name = bs.read_string(
            bs.read_uint8(),
            "cp1251",
            errors="ignore"
        )

        return {
            "player_id": player_id,
            "color": color,
            "is_npc": is_npc,
            "name": name
        }


    @staticmethod
    def init_game(bs: BitStream) -> dict | None:
        
        bs.skip_bits(72)
        d_spawns_available = bs.read_uint32()

        player_id = bs.read_uint16()

        bs.skip_bits(3)
        bs.skip_bits(272)

        hostname = bs.read_string(
            bs.read_uint8(),
            "cp1251",
            errors="ignore"
        )

        return {
            "player_id": player_id,
            "hostname": hostname,
            "d_spawns_available": d_spawns_available
        }


    @staticmethod
    def connection_rejected(bs: BitStream) -> dict | None:
        reason_kick = bs.read_uint8()

        return {
            "reason_kick": reason_kick
        }


    @staticmethod
    def set_spawn_info(bs: BitStream) -> dict | None:

        team = bs.read_uint8()
        skin = bs.read_uint32()

        unused = bs.read_uint8()

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()

        rotation = bs.read_float()

        weapon1 = bs.read_uint32()
        weapon2 = bs.read_uint32()
        weapon3 = bs.read_uint32()

        ammo1 = bs.read_uint32()
        ammo2 = bs.read_uint32()
        ammo3 = bs.read_uint32()

        return {
            "team": team,
            "skin": skin,


            "x": x,
            "y": y,
            "z": z,

            "rotation": rotation,

            "weapon1": weapon1,
            "weapon2": weapon2,
            "weapon3": weapon3,

            "ammo1": ammo1,
            "ammo2": ammo2,
            "ammo3": ammo3,
        }


    @staticmethod
    def request_spawn(bs: BitStream) -> dict | None:
        spawn_response = bs.read_uint8()

        return {
            "spawn_response": spawn_response
        }


    @staticmethod
    def client_message(bs: BitStream) -> dict | None:

        bs.skip_bits(32)

        message = bs.read_string(
            bs.read_uint32(),
            "cp1251",
            errors="ignore"
        )

        return {
            "message": message
        }


    @staticmethod
    def update_scores_and_pings(bs: BitStream) -> dict | None:
        entries = []

        while bs.remaining_bits >= 80:
            player_id = bs.read_uint16()
            score = bs.read_int32()
            ping = bs.read_uint32()

            entries.append({
                "player_id": int(player_id),
                "score": int(score),
                "ping": int(ping),
            })

        return {
            "state": "update_scores_and_pings",
            "scores_and_pings": entries,
            "count": len(entries),
        }


    @staticmethod
    def show_dialog(bs: BitStream) -> dict | None:
        dialog_id = bs.read_uint16()
        style = bs.read_uint8()

        title = bs.read_string(
            bs.read_uint8(),
            "cp1251",
            errors="ignore"
        )
        button1 = bs.read_string(
            bs.read_uint8(),
            "cp1251",
            errors="ignore"
        )
        button2 = bs.read_string(
            bs.read_uint8(),
            "cp1251",
            errors="ignore"
        )



        info = bs.read_compressed_string(max_chars=4096, encoding="cp1251")

        return {
            "dialog_id": dialog_id,
            "dialog_style": style,
            "dialog_title": title,
            "dialog_button1": button1,
            "dialog_button2": button2,
            "dialog_info": info,
        }


    @staticmethod
    def set_player_name(bs: BitStream) -> dict | None:
        player_id = bs.read_uint16()
        name = bs.read_string(
            bs.read_uint8(),
            "cp1251",
            errors="ignore"
        )

        success = bs.read_bool()

        return {
            "player_id": player_id,
            "name": name,
            "success": success
        }


    @staticmethod
    def set_player_pos(bs: BitStream) -> dict | None:

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()
        
        return {
            "x": x,
            "y": y,
            "z": z
        }


    @staticmethod
    def set_player_facing_angle(bs: BitStream) -> dict | None:

        rotation = bs.read_float()

        return {
            "rotation": rotation
        }

    @staticmethod
    def set_player_skin(bs: BitStream) -> dict | None:

        player_id = bs.read_uint32()
        skin_id = bs.read_uint32()

        return {
            "player_id": player_id,
            "skin": skin_id
        }

    @staticmethod
    def give_player_money(bs: BitStream) -> dict | None:
        amount = bs.read_int32()

        return {
            "state": "give_player_money",
            "amount": int(amount),
            "money_delta": int(amount),
        }


    @staticmethod
    def play_audio_stream(bs: BitStream) -> dict | None:
        
        url = bs.read_string(
            bs.read_uint8(),
            "ascii",
            errors="ignore"
        )


        return {
            "url": url,
        }


    @staticmethod
    def set_player_health(bs: BitStream) -> dict | None:

        health = bs.read_float()

        return {
            "health": float(health)
        }


    @staticmethod
    def set_player_armour(bs: BitStream) -> dict | None:

        armour = bs.read_float()

        return {
            "armour": armour
        }

    @staticmethod
    def set_weapon_ammo(bs: BitStream) -> dict | None:
        weapon_id = bs.read_uint8()
        ammo = bs.read_uint16()

        return {
            "weapon_id": weapon_id,
            "ammo": ammo
        }


    @staticmethod
    def set_camera_behind(bs: BitStream) -> dict:
        return {}

    @staticmethod
    def world_player_add(bs: BitStream) -> dict | None:
        player_id = bs.read_uint16()
        team = bs.read_uint8()
        skin_id = bs.read_uint32()

        pos_x = bs.read_float()
        pos_y = bs.read_float()
        pos_z = bs.read_float()

        facing_angle = bs.read_float()
        player_color = bs.read_uint32()
        fighting_style = bs.read_uint8()

        return {
            "state": "world_player_add",
            "player_id": int(player_id),
            "skin_id": int(skin_id),

            "xPlayer": float(pos_x),
            "yPlayer": float(pos_y),
            "zPlayer": float(pos_z),

            "x": float(pos_x),
            "y": float(pos_y),
            "z": float(pos_z),

            "facing_angle": float(facing_angle),
            "fighting_style": int(fighting_style),
        }


    @staticmethod
    def world_player_remove(bs: BitStream) -> dict | None:

        player_id = bs.read_uint16()

        return {
            "state": "world_player_remove",
            "player_id": int(player_id),
        }


    @staticmethod
    def world_vehicle_add(bs: BitStream) -> dict | None:
        vehicle_id = bs.read_uint16()
        model_id = bs.read_uint32()

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()
        rotation = bs.read_float()

        color1 = bs.read_uint8()
        color2 = bs.read_uint8()

        health = bs.read_float()
        interior = bs.read_uint8()

        return {
            "state": "world_vehicle_add",
            "vehicle_id": vehicle_id,
            "model_id": model_id,
            "CarX": x,
            "CarY": y,
            "CarZ": z,
            "rotation": rotation,
            "color1": color1,
            "color2": color2,
            "CarHealth": float(health),
            "interior": interior,
        }


    @staticmethod
    def world_vehicle_remove(bs: BitStream) -> dict | None:

        vehicle_id = bs.read_uint16()

        return {
            "state": "world_vehicle_remove",
            "vehicle_id": int(vehicle_id),
            "wVehicleID": int(vehicle_id),
        }


    @staticmethod
    def create_pickup(bs: BitStream) -> dict | None:
        pickup_id = bs.read_int32()
        model_id = bs.read_int32()
        spawn_type = bs.read_int32()

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()
        
        return {
            "state": "create_pickup",
            "pickup_id": int(pickup_id),
            "iPickupID": int(pickup_id),
            "model_id": int(model_id),
            "iModelID": int(model_id),
            "spawn_type": int(spawn_type),
            "iSpawnType": int(spawn_type),
            "xPickup": float(x),
            "yPickup": float(y),
            "zPickup": float(z),
        }


    @staticmethod
    def destroy_pickup(bs: BitStream) -> dict | None:

        pickup_id = bs.read_int32()

        return {
            "state": "destroy_pickup",
            "pickup_id": int(pickup_id),
            "iPickupID": int(pickup_id),
        }


    @staticmethod
    def set_map_icon(bs: BitStream) -> dict | None:
        icon_id = bs.read_uint8()

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()
        
        marker_type = bs.read_uint8()
        color = bs.read_uint32()
        style = bs.read_uint8()

        return {
            "state": "set_map_icon",
            "icon_id": icon_id,
            "xMAP": x,
            "yMAP": y,
            "zMAP": z,
            "marker_type": marker_type,
            "color": color,
            "color_hex": f"0x{color:08X}",
            "style": style,
        }


    @staticmethod
    def create_3d_text_label(bs: BitStream) -> dict | None:
        label_id = bs.read_uint16()
        color = bs.read_uint32()

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()

        draw_distance = bs.read_float()

        use_los_raw = bs.read_uint8()
        attached_player_id = bs.read_uint16()
        attached_vehicle_id = bs.read_uint16()

        text = bs.read_compressed_string(max_chars=4096, encoding="cp1251")

        return {
            "state": "create_3d_text_label",
            "label_id": int(label_id),
            "text_label_id": int(label_id),
            "color": int(color),
            "color_hex": f"0x{int(color) & 0xFFFFFFFF:08X}",
            "XLabel": float(x),
            "YLabel": float(y),
            "ZLabel": float(z),
            "draw_distance": float(draw_distance),
            "use_los": bool(use_los_raw),
            "use_los_raw": int(use_los_raw),
            "attached_player_id": int(attached_player_id),
            "attached_vehicle_id": int(attached_vehicle_id),
            "text": text,
            "label_text": text,
        }


    @staticmethod
    def delete_3d_text_label(bs: BitStream) -> dict | None:

        label_id = bs.read_uint16()

        return {
            "state": "delete_3d_text_label",
            "label_id": int(label_id),
            "text_label_id": int(label_id),
        }


    @staticmethod
    def set_interior(bs: BitStream) -> dict | None:

        interior_id = bs.read_uint8()

        return {
            "interior_id": interior_id
        }


    @staticmethod
    def set_camera_pos(bs: BitStream) -> dict | None:

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()
        
        return {
            "xCam": x,
            "yCam": y,
            "zCam": z
        }

    @staticmethod
    def enter_vehicle(bs: BitStream) -> dict | None:

        player_id = bs.read_uint16()
        vehicle_id = bs.read_uint16()
        is_passenger = bs.read_uint8()

        return {
            "state": "enter_vehicle",
            "player_id": int(player_id),
            "vehicle_id": int(vehicle_id),
            "wVehicleID": int(vehicle_id),
            "is_passenger": int(is_passenger),
            "passenger": int(is_passenger),
        }


    @staticmethod
    def put_player_in_vehicle(bs: BitStream) -> dict | None:

        vehicle_id = bs.read_uint16()
        seat_id = bs.read_uint8()

        return {
            "state": "put_player_in_vehicle",
            "vehicle_id": int(vehicle_id),
            "wVehicleID": int(vehicle_id),
            "seat_id": int(seat_id),
            "bSeatID": int(seat_id),
        }


    @staticmethod
    def set_vehicle_pos(bs: BitStream) -> dict | None:

        vehicle_id = bs.read_uint16()
        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()

        return {
            "state": "set_vehicle_pos",
            "vehicle_id": int(vehicle_id),
            "wVehicleID": int(vehicle_id),
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "XVehicle": float(x),
            "YVehicle": float(y),
            "ZVehicle": float(z),
        }


    @staticmethod
    def set_player_velocity(bs: BitStream) -> dict | None:

        velocity_x = bs.read_float()
        velocity_y = bs.read_float()
        velocity_z = bs.read_float()

        return {
            "state": "set_player_velocity",

            "velocity_x": float(velocity_x),
            "velocity_y": float(velocity_y),
            "velocity_z": float(velocity_z),

            "velocity": (
                float(velocity_x),
                float(velocity_y),
                float(velocity_z),
            ),
        }


    @staticmethod
    def set_vehicle_velocity(bs: BitStream) -> dict | None:

        turn = bs.read_uint8()

        velocity_x = bs.read_float()
        velocity_y = bs.read_float()
        velocity_z = bs.read_float()

        return {
            "state": "set_vehicle_velocity",
            "turn": int(turn),

            "velocity_x_car": float(velocity_x),
            "velocity_y_car": float(velocity_y),
            "velocity_z_car": float(velocity_z),

            "velocity": (
                float(velocity_x),
                float(velocity_y),
                float(velocity_z),
            ),
        }


    @staticmethod
    def reset_player_money(bs: BitStream) -> dict | None:

        return {
            "state": "reset_player_money",
        }

    @staticmethod
    def show_text_draw(bs: BitStream) -> dict | None:
        wTextDrawID = bs.read_uint16()
        flags = bs.read_uint8()
        fLetterWidth = bs.read_float()
        fLetterHeight = bs.read_float()
        dLetterColor = bs.read_uint32()
        fLineWidth = bs.read_float()
        fLineHeight = bs.read_float()
        dBoxColor = bs.read_uint32()
        shadow = bs.read_uint8()
        outline = bs.read_uint8()
        dBackgroundColor = bs.read_uint32()
        style = bs.read_uint8()
        selectable = bs.read_uint8()
        fX = bs.read_float()
        fY = bs.read_float()
        wModelID = bs.read_uint16()
        fRotX = bs.read_float()
        fRotY = bs.read_float()
        fRotZ = bs.read_float()
        fZoom = bs.read_float()
        wColor1 = bs.read_uint16()
        wColor2 = bs.read_uint16()
        szTextLen = bs.read_uint16()
        szText = bs.read_string(szTextLen, "cp1251", errors="ignore") if szTextLen > 0 else ""

        return {
            "state": "show_text_draw",
            "wTextDrawID": wTextDrawID,
            "textdraw_id": wTextDrawID,
            "flags": flags,
            "fLetterWidth": fLetterWidth,
            "fLetterHeight": fLetterHeight,
            "dLetterColor": dLetterColor,
            "fLineWidth": fLineWidth,
            "fLineHeight": fLineHeight,
            "dBoxColor": dBoxColor,
            "shadow": shadow,
            "outline": outline,
            "dBackgroundColor": dBackgroundColor,
            "style": style,
            "selectable": selectable,
            "fX": fX,
            "fY": fY,
            "wModelID": wModelID,
            "fRotX": fRotX,
            "fRotY": fRotY,
            "fRotZ": fRotZ,
            "fZoom": fZoom,
            "wColor1": wColor1,
            "wColor2": wColor2,
            "szTextLen": szTextLen,
            "szText": szText,
        }

    @staticmethod
    def text_draw_set_string(bs: BitStream) -> dict | None:
        wTextDrawID = bs.read_uint16()
        textLength = bs.read_uint16()
        text = bs.read_string(textLength, "cp1251", errors="ignore") if textLength > 0 else ""

        return {
            "state": "text_draw_set_string",
            "wTextDrawID": wTextDrawID,
            "textdraw_id": wTextDrawID,
            "textLength": textLength,
            "text": text,
        }

    @staticmethod
    def hide_text_draw(bs: BitStream) -> dict | None:
        wTextDrawID = bs.read_uint16()

        return {
            "state": "hide_text_draw",
            "wTextDrawID": wTextDrawID,
            "textdraw_id": wTextDrawID,
        }

    @staticmethod
    def set_vehicle_params(bs: BitStream) -> dict | None:

        vehicle_id = bs.read_uint16()

        params = []
        params_format = "int32"

        while bs.remaining_bits >= 32:
            params.append(int(bs.read_int32()))

        raw_extra = b""
        if bs.remaining_bits >= 8:
            raw_extra = bs.read_bytes(bs.remaining_bits // 8)

        result = {
            "state": "set_vehicle_params",
            "vehicle_id": int(vehicle_id),
            "params": params,
            "params_format": params_format,
            "raw_extra": raw_extra.hex(),
        }

        names = (
            "engine",
            "lights",
            "alarm",
            "doors",
            "bonnet",
            "boot",
            "objective",
            "siren",
        )

        for index, name in enumerate(names):
            if index < len(params):
                result[name] = params[index]

        return result



RPC_PARSERS = {
    RPCConstants.REQUEST_SPAWN: RPCParser.request_spawn,
    RPCConstants.UPDATE_SCORES_PINGS_IPS: RPCParser.update_scores_and_pings,
    RPCConstants.SCR_GIVE_PLAYER_MONEY: RPCParser.give_player_money,
    RPCConstants.SCR_DIALOG_BOX: RPCParser.show_dialog,
    RPCConstants.CLIENT_MESSAGE: RPCParser.client_message,
    RPCConstants.SERVER_QUIT: RPCParser.server_quit,
    RPCConstants.CONNECTION_REJECTED: RPCParser.connection_rejected,
    RPCConstants.SERVER_JOIN: RPCParser.server_join,
    RPCConstants.INIT_GAME: RPCParser.init_game,
    RPCConstants.SCR_SET_SPAWN_INFO: RPCParser.set_spawn_info,
    RPCConstants.SCR_SET_PLAYER_NAME: RPCParser.set_player_name,
    RPCConstants.SCR_SET_PLAYER_POS: RPCParser.set_player_pos,
    RPCConstants.SCR_SET_PLAYER_FACING_ANGLE: RPCParser.set_player_facing_angle,
    RPCConstants.SCR_SET_PLAYER_SKIN: RPCParser.set_player_skin,
    RPCConstants.PLAY_AUDIO_STREAM: RPCParser.play_audio_stream,
    RPCConstants.SCR_SET_PLAYER_HEALTH: RPCParser.set_player_health,
    RPCConstants.SCR_SET_PLAYER_ARMOUR: RPCParser.set_player_armour,
    RPCConstants.SCR_SET_WEAPON_AMMO: RPCParser.set_weapon_ammo,
    RPCConstants.SCR_SET_CAMERA_BEHIND_PLAYER: RPCParser.set_camera_behind,
    RPCConstants.WORLD_PLAYER_ADD: RPCParser.world_player_add,
    RPCConstants.WORLD_PLAYER_REMOVE: RPCParser.world_player_remove,
    RPCConstants.WORLD_VEHICLE_ADD: RPCParser.world_vehicle_add,
    RPCConstants.WORLD_VEHICLE_REMOVE: RPCParser.world_vehicle_remove,
    RPCConstants.SCR_SET_MAP_ICON: RPCParser.set_map_icon,
    RPCConstants.CREATE_PICKUP: RPCParser.create_pickup,
    RPCConstants.DESTROY_PICKUP: RPCParser.destroy_pickup,
    RPCConstants.SCR_CREATE_3D_TEXT_LABEL: RPCParser.create_3d_text_label,
    RPCConstants.SCR_DELETE_3D_TEXT_LABEL: RPCParser.delete_3d_text_label,
    RPCConstants.SCR_SET_INTERIOR: RPCParser.set_interior,
    RPCConstants.SCR_SET_CAMERA_POS: RPCParser.set_camera_pos,
    RPCConstants.ENTER_VEHICLE: RPCParser.enter_vehicle,
    RPCConstants.SCR_PUT_PLAYER_IN_VEHICLE: RPCParser.put_player_in_vehicle,
    RPCConstants.SCR_SET_VEHICLE_POS: RPCParser.set_vehicle_pos,
    RPCConstants.SCR_SET_PLAYER_VELOCITY: RPCParser.set_player_velocity,
    RPCConstants.SCR_SET_VEHICLE_VELOCITY: RPCParser.set_vehicle_velocity,
    RPCConstants.SCR_VEHICLE_PARAMS: RPCParser.set_vehicle_params,
    RPCConstants.SCR_RESET_MONEY: RPCParser.reset_player_money,
    RPCConstants.SCR_SHOW_TEXT_DRAW: RPCParser.show_text_draw,
    RPCConstants.SCR_TEXT_DRAW_SET_STRING: RPCParser.text_draw_set_string,
    RPCConstants.SCR_HIDE_TEXT_DRAW: RPCParser.hide_text_draw,
}


class RPC:

    @staticmethod
    def _read_rpc_id(
        bs: BitStream
    ) -> tuple[int, int]:

        rpc_id = bs.read_bits(8)
        skip = bs.read_bits(2)
        return rpc_id, skip

    @staticmethod
    def _bits_to_bytes(value: int, bitlen: int) -> bytes:
        if bitlen <= 0:
            return b""

        count = (bitlen + 7) // 8
        pad = count * 8 - bitlen

        if pad:
            value <<= pad

        return value.to_bytes(count, "big")

    @staticmethod
    def _parse_payload(
        rpc_id: int,
        payload: bytes
    ) -> tuple[dict | None, BitStream | None]:
        rpc_parser = RPC_PARSERS.get(rpc_id)

        if rpc_parser is None:
            return None, None

        payload_bs = BitStream(payload)

        try:
            return rpc_parser(payload_bs), payload_bs
        except Exception as error:
            logger.rpc_parse_error(
                f"RPC PAYLOAD PARSE ERROR"
                f"id={rpc_id} parser={rpc_parser.__name__}: {error}"
            )
            return None, payload_bs

    @staticmethod
    def read_rpc(data: bytes) -> dict | None:

        if len(data) < 3:
            return None

        try:

            bs = BitStream(data)

            rpc_id, skip = RPC._read_rpc_id(bs)

            bitlen = bs.read_compressed(16, unsigned=True)

            if bitlen > bs.remaining_bits:
                logger.rpc_parse_error(
                    f"RPC ERROR Not enough bits: "
                    f"need {bitlen}, have {bs.remaining_bits} "
                    f"rpc_id={rpc_id} skip={skip} "
                    f"body_len={len(data)} "
                    f"first_4_bytes={data[:4].hex()}"
                )
                return None

            payload_value = bs.read_bits(bitlen)
            payload_bytes = RPC._bits_to_bytes(payload_value, bitlen)

            parsed_payload, payload_bs = RPC._parse_payload(
                rpc_id,
                payload_bytes
            )
            effective_bitlen = bitlen

            if payload_bs is not None:
                effective_bitlen = payload_bs.bitpos - payload_bs.skipped_bits

            return {
                "rpc_id": rpc_id,
                "skip": skip,
                "bitlen": effective_bitlen,
                "payload": payload_bytes,
                "parsed_payload": parsed_payload,
                "raw": data,
            }

        except Exception as e:

            logger.rpc_parse_error(f"{e}")

            return None

class PacketParser:

    @staticmethod
    def open_connection_reply(
        data: bytes
    ) -> dict:

        return {
            "type": "open_connection_reply",
            "raw": data
        }

    @staticmethod
    def open_connection_cookie(
        data: bytes
    ) -> dict | None:

        if len(data) < 2:
            return None

        cookie = (data[0] << 8) | data[1]

        return {
            "type": "open_connection_cookie",
            "cookie": cookie,
            "raw": data
        }

    @staticmethod
    def auth_key(
        data: bytes
    ) -> dict | None:

        if len(data) < 2:
            return None

        key_len = data[0]

        if key_len == 0 or key_len > 255:
            return None

        if len(data) < 1 + key_len:
            return None

        key_bytes = data[1:1 + key_len]

        key = key_bytes.rstrip(b"\x00").decode(
            "ascii",
            errors="ignore"
        )

        return {
            "type": "auth_key",
            "key": key,
            "key_len": key_len,
            "raw": data
        }

    @staticmethod
    def connection_request_accepted(
        data: bytes
    ) -> dict | None:

        if len(data) < 12:
            return None

        bs = BitStream(data)
        binary_address = bs.read_uint32()
        port = bs.read_uint16()
        player_index = bs.read_uint16()
        server_challenge = bs.read_uint32()

        return {
            "type": "connection_request_accepted",
            "binary_address": binary_address,
            "port": port,
            "player_index": player_index,
            "server_challenge": server_challenge,
            "raw": data
        }

    @staticmethod
    def internal_ping(
        data: bytes
    ) -> dict | None:

        if len(data) < 4:
            return None

        bs = BitStream(data)
        sender_ms = bs.read_uint32()

        return {
            "type": "internal_ping",
            "sender_ms": sender_ms,
            "raw": data
        }

    @staticmethod
    def connected_pong(
        data: bytes
    ) -> dict | None:

        if len(data) < 8:
            return None

        bs = BitStream(data)
        receiver_ms = bs.read_uint32()
        sender_ms = bs.read_uint32()

        return {
            "type": "connected_pong",
            "receiver_ms": receiver_ms,
            "sender_ms": sender_ms,
            "raw": data
        }

    @staticmethod
    def disconnection_notification(
        data: bytes
    ) -> dict:

        reason = (
            data.decode(
                "ascii",
                errors="ignore"
            )
            if data else "No reason provided"
        )

        return {
            "type": "disconnection_notification",
            "reason": reason,
            "raw": data
        }

    @staticmethod
    def vehicle_sync(
        data: bytes
    ) -> dict | None:

        bs = BitStream(data)

        player_id = bs.read_uint16()
        vehicle_id = bs.read_uint16()
        lr = bs.read_uint16()
        ud = bs.read_uint16()
        keys = bs.read_uint16()

        quat_cw_neg = bs.read_bool()
        quat_cx_neg = bs.read_bool()
        quat_cy_neg = bs.read_bool()
        quat_cz_neg = bs.read_bool()

        quat_cx = bs.read_uint16()
        quat_cy = bs.read_uint16()
        quat_cz = bs.read_uint16()

        qx = quat_cx / 65535.0
        qy = quat_cy / 65535.0
        qz = quat_cz / 65535.0
        if quat_cx_neg:
            qx = -qx
        if quat_cy_neg:
            qy = -qy
        if quat_cz_neg:
            qz = -qz
        qw = math.sqrt(max(0.0, 1.0 - qx * qx - qy * qy - qz * qz))
        if quat_cw_neg:
            qw = -qw

        x = bs.read_float()
        y = bs.read_float()
        z = bs.read_float()

        velocity_magnitude = bs.read_float()

        if velocity_magnitude != 0.0:
            speed_x = bs.read_uint16()
            speed_y = bs.read_uint16()
            speed_z = bs.read_uint16()

            velocity_x = (speed_x / 32767.5 - 1.0) * velocity_magnitude
            velocity_y = (speed_y / 32767.5 - 1.0) * velocity_magnitude
            velocity_z = (speed_z / 32767.5 - 1.0) * velocity_magnitude
        else:
            velocity_x = 0.0
            velocity_y = 0.0
            velocity_z = 0.0

        health = float(bs.read_uint16())

        health_armour_byte = bs.read_uint8()
        health_nibble = (health_armour_byte >> 4) & 0x0F
        armour_nibble = health_armour_byte & 0x0F

        if health_nibble == 0x0F:
            player_health = 100
        elif health_nibble == 0x00:
            player_health = 0
        else:
            player_health = health_nibble * 7

        if armour_nibble == 0x0F:
            player_armour = 100
        elif armour_nibble == 0x00:
            player_armour = 0
        else:
            player_armour = armour_nibble * 7

        return {
            "type": "vehicle_sync",
            "packet_id": PacketID.VEHICLE_SYNC,
            "player_id": player_id,
            "vehicle_id": vehicle_id,
            "wVehicleID": vehicle_id,
            "lr": lr,
            "ud": ud,
            "keys": keys,
            "quat_w": qw,
            "quat_x": qx,
            "quat_y": qy,
            "quat_z": qz,
            "CarX": x,
            "CarY": y,
            "CarZ": z,
            "velocity_x": velocity_x,
            "velocity_y": velocity_y,
            "velocity_z": velocity_z,
            "CarHealth": health,
            "health": player_health,
            "armour": player_armour,
            "raw": data,
        }

    @staticmethod
    def rpc(
        data: bytes
    ) -> dict | None:

        parsed = RPC.read_rpc(data)

        if parsed is None:
            return None

        return {
            "type": "rpc",
            "rpc_id": parsed["rpc_id"],
            "skip_bits": parsed["skip"],
            "bitlen": parsed["bitlen"],
            "payload": parsed["payload"],
            "parsed_payload": parsed["parsed_payload"],
            "raw": data
        }


PACKET_PARSERS = {
    PacketID.OPEN_CONNECTION_REPLY: PacketParser.open_connection_reply,
    PacketID.OPEN_CONNECTION_COOKIE: PacketParser.open_connection_cookie,
    PacketID.AUTH_KEY: PacketParser.auth_key,
    PacketID.CONNECTION_REQUEST_ACCEPTED: PacketParser.connection_request_accepted,
    PacketID.INTERNAL_PING: PacketParser.internal_ping,
    PacketID.CONNECTED_PONG: PacketParser.connected_pong,
    PacketID.DISCONNECTION_NOTIFICATION: PacketParser.disconnection_notification,
    PacketID.RPC: PacketParser.rpc,
    PacketID.VEHICLE_SYNC: PacketParser.vehicle_sync,
}


def parse_packet(data: bytes) -> dict:

    if not data:
        return {"type": "unknown"}

    packet_id = data[0]

    parser = PACKET_PARSERS.get(packet_id)

    if parser:
        result = parser(data[1:])

        if result is not None:
            result["packet_id"] = packet_id
            return result

    return {
        "type": "packet",
        "packet_id": packet_id,
        "data": data[1:]
    }
