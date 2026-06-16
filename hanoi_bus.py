"""
Hanoi bus real-time arrival info via BusMap API.

Fetches upcoming vehicles for a given stop (trạm) and produces
Vietnamese announcement text ready to feed into MisoTTS.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Optional

import urllib.request
import urllib.error
import json

BUSMAP_API_BASE = os.environ.get("BUSMAP_API_BASE", "https://api.busmap.vn")

# GET /api/v1/trackers/route/stops/{stop_id}
# Returns list of routes with upcoming vehicles for that stop.
_STOP_TRACKER_PATH = "/api/v1/trackers/route/stops/{stop_id}"


@dataclasses.dataclass
class VehicleArrival:
    plate: str          # biển số xe, e.g. "29E-760.74"
    speed_kmh: float    # tốc độ (km/h)
    distance_km: float  # khoảng cách đến trạm (km)
    eta_minutes: int    # thời gian còn lại (phút)


@dataclasses.dataclass
class RouteTracker:
    route_id: str               # e.g. "49"
    route_name: str             # e.g. "Tuyến xe 49"
    direction: str              # "lượt đi" | "lượt về"
    start_point: str            # điểm đầu
    end_point: str              # điểm cuối
    vehicles: list[VehicleArrival]


def _parse_response(data: dict) -> list[RouteTracker]:
    """Parse BusMap tracker JSON into RouteTracker objects."""
    routes: list[RouteTracker] = []

    payload = data.get("data") or data.get("result") or data
    if isinstance(payload, dict):
        payload = payload.get("routes") or payload.get("items") or []

    for r in payload:
        vehicles = []
        for v in r.get("vehicles") or r.get("vehicleList") or []:
            plate = (
                v.get("plateNumber")
                or v.get("plate")
                or v.get("bienSo")
                or v.get("licensePlate")
                or ""
            )
            speed = float(
                v.get("speed") or v.get("tocDo") or v.get("vehicleSpeed") or 0
            )
            distance = float(
                v.get("distance")
                or v.get("khoangCach")
                or v.get("distanceToStop")
                or 0
            )
            eta = int(
                v.get("etaMinutes")
                or v.get("timeRemaining")
                or v.get("thoiGianConLai")
                or v.get("time")
                or 0
            )
            vehicles.append(
                VehicleArrival(
                    plate=plate,
                    speed_kmh=speed,
                    distance_km=distance,
                    eta_minutes=eta,
                )
            )

        direction_raw = (
            r.get("direction")
            or r.get("luot")
            or r.get("directionName")
            or ""
        )
        if isinstance(direction_raw, int):
            direction = "lượt đi" if direction_raw == 1 else "lượt về"
        else:
            direction = str(direction_raw) if direction_raw else "lượt đi"

        routes.append(
            RouteTracker(
                route_id=str(r.get("routeId") or r.get("id") or r.get("routeNo") or ""),
                route_name=(
                    r.get("routeName")
                    or r.get("name")
                    or r.get("tenTuyen")
                    or f"Tuyến {r.get('routeId', '')}"
                ),
                direction=direction,
                start_point=(
                    r.get("startPoint")
                    or r.get("diemDau")
                    or r.get("fromStation")
                    or ""
                ),
                end_point=(
                    r.get("endPoint")
                    or r.get("diemCuoi")
                    or r.get("toStation")
                    or ""
                ),
                vehicles=vehicles,
            )
        )

    return routes


def fetch_stop_tracker(
    stop_id: str | int,
    *,
    api_key: Optional[str] = None,
    timeout: int = 10,
) -> list[RouteTracker]:
    """
    Fetch real-time bus arrivals for *stop_id* from BusMap.

    Args:
        stop_id: Numeric BusMap stop ID (e.g. 4 for a Hanoi stop).
        api_key: Optional Bearer/API key if required by the endpoint.
        timeout: HTTP request timeout in seconds.

    Returns:
        List of RouteTracker objects, one per route serving the stop.
    """
    url = BUSMAP_API_BASE + _STOP_TRACKER_PATH.format(stop_id=stop_id)
    headers = {"Accept": "application/json", "User-Agent": "MisoTTS/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"BusMap API error {exc.code} for stop {stop_id}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach BusMap API ({url}): {exc.reason}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from BusMap API: {exc}") from exc

    return _parse_response(data)


# ---------------------------------------------------------------------------
# Vietnamese TTS text formatters
# ---------------------------------------------------------------------------

def _format_vehicle(v: VehicleArrival) -> str:
    plate = v.plate
    speed = int(v.speed_kmh)
    dist = f"{v.distance_km:.2f}".rstrip("0").rstrip(".")
    minutes = v.eta_minutes

    if minutes <= 1:
        eta_text = "sắp đến trạm"
    else:
        eta_text = f"còn khoảng {minutes} phút"

    return (
        f"xe biển số {plate}, đang đi {speed} ki lô mét một giờ, "
        f"cách trạm {dist} ki lô mét, {eta_text}"
    )


def format_stop_announcement(
    stop_name: str,
    routes: list[RouteTracker],
    max_vehicles_per_route: int = 2,
) -> str:
    """
    Build a natural Vietnamese TTS announcement for a bus stop.

    Example output:
        "Thông tin xe buýt tại trạm Nhà C6 KĐT Mỹ Đình Một.
         Tuyến 49 lượt đi Trần Khánh Dư đi Nhổn:
         xe biển số 29E-760.74, đang đi 0 ki lô mét một giờ, cách trạm 1.89 ki lô mét, sắp đến trạm.
         ..."
    """
    lines: list[str] = [f"Thông tin xe buýt tại trạm {stop_name}."]

    for route in routes:
        vehicles = route.vehicles[:max_vehicles_per_route]
        if not vehicles:
            continue

        route_header = f"Tuyến {route.route_id} {route.direction}"
        if route.start_point and route.end_point:
            route_header += f", {route.start_point} đi {route.end_point}"
        route_header += ":"
        lines.append(route_header)

        for v in vehicles:
            lines.append(_format_vehicle(v))

    if len(lines) == 1:
        lines.append("Hiện tại không có xe nào sắp đến trạm này.")

    return " ".join(lines)
