"""
Generate a Vietnamese bus-arrival TTS announcement using BusMap + MisoTTS.

Usage:
    python bus_announcement.py --stop-id 4 --stop-name "Nhà C6 KĐT Mỹ Đình I"

Set BUSMAP_API_BASE env var to override the default API host.
Set BUSMAP_API_KEY  env var if your BusMap account requires an API key.
"""

import argparse
import os

os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ["NO_TORCH_COMPILE"] = "1"

import torch
import torchaudio  # type: ignore

from generator import DEFAULT_MISO_TTS_REPO_ID, Segment, load_miso_8b
from hanoi_bus import fetch_stop_tracker, format_stop_announcement


def main() -> None:
    parser = argparse.ArgumentParser(description="Hanoi bus TTS announcement")
    parser.add_argument(
        "--stop-id",
        required=True,
        help="BusMap stop ID (e.g. 4)",
    )
    parser.add_argument(
        "--stop-name",
        default="",
        help="Human-readable stop name for the announcement",
    )
    parser.add_argument(
        "--output",
        default="bus_announcement.wav",
        help="Output WAV file path",
    )
    parser.add_argument(
        "--max-vehicles",
        type=int,
        default=2,
        help="Max upcoming vehicles to announce per route",
    )
    parser.add_argument(
        "--speaker",
        type=int,
        default=0,
        help="MisoTTS speaker ID (0 or 1)",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 1. Fetch real-time bus data from BusMap
    # ------------------------------------------------------------------
    api_key = os.environ.get("BUSMAP_API_KEY")
    print(f"Fetching bus info for stop ID {args.stop_id} …")
    try:
        routes = fetch_stop_tracker(args.stop_id, api_key=api_key)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1) from exc

    stop_name = args.stop_name or f"trạm {args.stop_id}"
    text = format_stop_announcement(
        stop_name,
        routes,
        max_vehicles_per_route=args.max_vehicles,
    )
    print(f"\nAnnouncement text:\n{text}\n")

    # ------------------------------------------------------------------
    # 2. Synthesise speech with MisoTTS
    # ------------------------------------------------------------------
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading MisoTTS on {device} …")
    model_source = os.environ.get("MISO_TTS_8B_MODEL", DEFAULT_MISO_TTS_REPO_ID)
    generator = load_miso_8b(device, model_path_or_repo_id=model_source)

    audio = generator.generate(
        text=text,
        speaker=args.speaker,
        context=[],
        max_audio_length_ms=30_000,
    )

    torchaudio.save(
        args.output,
        audio.unsqueeze(0).cpu(),
        generator.sample_rate,
    )
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
