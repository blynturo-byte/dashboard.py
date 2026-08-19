from .parsers import parse_packet as samp_parse_packet
from .constants import RPC as RPCConstants


class SampPacketHandler:

    CONNECTION_REJECTED_REASONS = {
        1: "Incorrect client version",
        2: "This account is already logged in",
        3: "Bad mod version",
        4: "No free player slots available",
    }

    def _emit_connection_rejected_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        parsed = result.get("parsed_payload")

        if not parsed or "reason_kick" not in parsed:
            return

        try:
            reason_code = int(parsed.get("reason_kick"))
        except Exception:
            reason_code = -1

        reason_text = self.CONNECTION_REJECTED_REASONS.get(
            reason_code,
            f"Unknown reason ({reason_code})",
        )

        self.session._emit_callback(
            "onConnectionRejected",
            reason_code,
            reason_text,
            parsed,
            result,
        )

        self.session._emit_callback(
            "onKick",
            reason_code,
            reason_text,
            parsed,
            result,
        )

    def _emit_show_dialog_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if "dialog_id" not in parsed or "dialog_info" not in parsed:
            return

        dialog_id = parsed.get("dialog_id")
        dialog_style = parsed.get("dialog_style")
        title = parsed.get("dialog_title", "")
        info = parsed.get("dialog_info", "")
        button1 = parsed.get("dialog_button1", "")
        button2 = parsed.get("dialog_button2", "")



        self.session._emit_callback(
            "onShowDialog",
            dialog_id,
            dialog_style,
            title,
            info,
            button1,
            button2,
            parsed,
            result,
        )

    def _stop_coord_movement_on_dialog(self, result: dict) -> None:
        dialog_type = None
        if result.get("type") == "rpc":
            parsed = result.get("parsed_payload") or {}
            if "dialog_id" in parsed and "dialog_info" in parsed:
                dialog_type = "show_dialog"

        if dialog_type is not None:
            self.api._handle_coord_movement_dialog(dialog_type)

    def _emit_show_text_draw_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.SCR_SHOW_TEXT_DRAW:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "show_text_draw":
            return

        self.session._emit_callback(
            "OnShowTextDraw",
            parsed.get("textdraw_id"),
            parsed.get("style"),
            bool(parsed.get("selectable")),
            parsed.get("wModelID"),
            parsed,
            result,
        )

    def _emit_show_chat_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if "message" not in parsed:
            return

        message = parsed.get("message", "")

        self.session._emit_callback(
            "onShowChat",
            message,
            parsed,
            result,
        )


    def _emit_vehicle_stream_in_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.WORLD_VEHICLE_ADD:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "world_vehicle_add":
            return

        self.session._emit_callback(
            "onVehicleStreamIn",
            parsed.get("model_id"),
            parsed.get("vehicle_id"),
            parsed.get("CarX"),
            parsed.get("CarY"),
            parsed.get("CarZ"),
        )


    def _emit_player_stream_in_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.WORLD_PLAYER_ADD:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "world_player_add":
            return

        x = parsed.get("xPlayer", parsed.get("x"))
        y = parsed.get("yPlayer", parsed.get("y"))
        z = parsed.get("zPlayer", parsed.get("z"))

        for event_name in ("OnPlayerStreamIn", "onPlayerStreamIn"):
            self.session._emit_callback(
                event_name,
                parsed.get("player_id"),
                parsed.get("skin_id"),
                x,
                y,
                z,
            )


    def _emit_set_map_icon_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.SCR_SET_MAP_ICON:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "set_map_icon":
            return

        x = parsed.get("x", parsed.get("xMAP"))
        y = parsed.get("y", parsed.get("yMAP"))
        z = parsed.get("z", parsed.get("zMAP"))
        xyz = parsed.get("xyz") or (x, y, z)

        self.session._emit_callback(
            "onSetMapIcon",
            parsed.get("icon_id"),
            xyz,
            parsed.get("marker_type"),
            parsed.get("style"),
            parsed,
            result,
        )

    def _emit_create_3d_text_label_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.SCR_CREATE_3D_TEXT_LABEL:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "create_3d_text_label":
            return

        self.session._emit_callback(
            "onCreate3DTextLabel",
            parsed.get("label_id"),
            parsed.get("text", parsed.get("label_text", "")),
            parsed.get("color"),
            parsed.get("XLabel"),
            parsed.get("YLabel"),
            parsed.get("ZLabel"),
            parsed.get("draw_distance"),
            parsed.get("use_los"),
            parsed.get("attached_player_id"),
            parsed.get("attached_vehicle_id"),
            parsed,
            result,
        )


    def _emit_enter_vehicle_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.ENTER_VEHICLE:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "enter_vehicle":
            return

        self.session._emit_callback(
            "onPlayerEnterVehicle",
            parsed.get("player_id"),
            parsed.get("vehicle_id"),
            parsed.get("is_passenger", parsed.get("passenger", 0)),
            parsed,
            result,
        )

    def _emit_put_player_in_vehicle_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.SCR_PUT_PLAYER_IN_VEHICLE:
            return

        parsed = result.get("parsed_payload")

        if not parsed:
            return

        if parsed.get("state") != "put_player_in_vehicle":
            return

        self.session._emit_callback(
            "onPutPlayerInVehicle",
            parsed.get("vehicle_id"),
            parsed.get("seat_id"),
            parsed,
            result,
        )

    def _emit_set_player_health_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.SCR_SET_PLAYER_HEALTH:
            return

        parsed = result.get("parsed_payload")

        if not parsed or "health" not in parsed:
            return

        self.session._emit_callback(
            "OnSetPlayerHealth",
            parsed.get("health"),
        )

    def _emit_set_player_armour_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        if result.get("rpc_id") != RPCConstants.SCR_SET_PLAYER_ARMOUR:
            return

        parsed = result.get("parsed_payload")

        if not parsed or "armour" not in parsed:
            return

        self.session._emit_callback(
            "OnSetPlayerArmour",
            parsed.get("armour"),
        )

    def __init__(self, session):
        self.session = session

        self._rpc_router = {
            RPCConstants.CONNECTION_REJECTED: self._emit_connection_rejected_event,
            RPCConstants.ENTER_VEHICLE: self._emit_enter_vehicle_event,
            RPCConstants.SCR_PUT_PLAYER_IN_VEHICLE: self._emit_put_player_in_vehicle_event,
            RPCConstants.SCR_SET_PLAYER_HEALTH: self._emit_set_player_health_event,
            RPCConstants.SCR_SET_PLAYER_ARMOUR: self._emit_set_player_armour_event,
            RPCConstants.WORLD_PLAYER_ADD: self._emit_player_stream_in_event,
            RPCConstants.WORLD_VEHICLE_ADD: self._emit_vehicle_stream_in_event,
            RPCConstants.SCR_SET_MAP_ICON: self._emit_set_map_icon_event,
            RPCConstants.SCR_CREATE_3D_TEXT_LABEL: self._emit_create_3d_text_label_event,
            RPCConstants.SCR_DIALOG_BOX: self._emit_dialog_handlers,
            RPCConstants.SCR_SHOW_TEXT_DRAW: self._emit_show_text_draw_event,
            RPCConstants.CLIENT_MESSAGE: self._emit_show_chat_event,
            RPCConstants.INIT_GAME: self._handle_init_game,
        }

    @property
    def api(self):
        return self.session.api

    def _check_disconnection(self, result: dict) -> bool:
        if result and result.get("type") == "disconnection_notification":
            reason = result.get("reason", "Unknown reason")

            self.session.connected = False
            self.session._emit_callback("disconnect")
            return True

        return False

    def _attach_raknet_metadata(self, result: dict, raknet_packet: dict) -> None:
        result["_msg_num"] = raknet_packet.get("message_number")
        result["_reliability"] = raknet_packet.get("reliability")
        result["_ordering_channel"] = raknet_packet.get("ordering_channel")
        result["_ordering_index"] = raknet_packet.get("ordering_index")

    def _emit_receive_event(self, body: bytes) -> None:
        packet_id = body[0] if body else None
        payload = body[1:] if body else b""

        self.session._emit_callback(
            "onReceivePacket",
            packet_id,
            payload,
            key=packet_id,
        )

    def _emit_receive_rpc_event(self, result: dict) -> None:
        if result.get("type") != "rpc":
            return

        rpc_id = result.get("rpc_id")

        self.session._emit_callback(
            "onReceiveRPC",
            rpc_id,
            result.get("payload", b""),
            key=rpc_id,
        )

    def _update_managers(self, result: dict) -> None:
        self.session.server_info.process_packet(result)
        self.session.stream.process_packet(result)
        self.session.players.process_packet(result, stream_info=self.session.stream)
        self.session.chat.process_packet(result)

    def _handle_init_game(self, result: dict) -> None:
        if (
            result.get("type") == "rpc"
            and result.get("rpc_id") == RPCConstants.INIT_GAME
        ):
            self.session.mark_init_game_received()
            self.session._emit_callback("onconnect")

            self.session.send_rpc_request_class(0)

    def _handle_open_connection_cookie(self, result: dict) -> None:
        if result.get("type") != "open_connection_cookie":
            return

        cookie = result.get("cookie", 0x6969)
        self.session.send_open_connection_request(cookie=cookie)

    def _handle_internal_ping(self, result: dict) -> None:
        if result.get("type") != "internal_ping":
            return

        sender_ms = result.get("sender_ms", 0)
        receiver_ms = self.session.session_ms()

        if self.session.connected:

            self.session.send_connected_pong(
                receiver_ms,
                sender_ms
            )

    def _emit_dialog_handlers(self, result: dict) -> None:
        self._stop_coord_movement_on_dialog(result)
        self._emit_show_dialog_event(result)

    def _dispatch_rpc_handlers(self, result: dict) -> None:
        handler = self._rpc_router.get(result.get("rpc_id"))
        if handler is not None:
            handler(result)

    def _handle_by_type(self, result: dict) -> None:
        ptype = result.get("type")

        if ptype == "rpc":
            self._emit_receive_rpc_event(result)
            self._update_managers(result)
            self._dispatch_rpc_handlers(result)
            return

        if ptype == "internal_ping":
            self._handle_internal_ping(result)
            return

        if ptype == "open_connection_cookie":
            self._handle_open_connection_cookie(result)
            return

        self._update_managers(result)

    def process_packet(self, raknet_packet: dict) -> dict | None:
        if raknet_packet.get("type") == "ack":
            return raknet_packet

        body = raknet_packet.get("data", b"")

        if not body:
            return None

        self._emit_receive_event(body)

        result = samp_parse_packet(body)

        if not result:
            return None

        if self._check_disconnection(result):
            return result

        self._attach_raknet_metadata(result, raknet_packet)

        self._handle_by_type(result)

        return result
