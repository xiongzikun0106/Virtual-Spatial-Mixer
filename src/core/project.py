import json
from dataclasses import dataclass, field


@dataclass
class TrackState:
    track_id: int
    filepath: str
    name: str
    color_index: int
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    priority: int = 0
    muted: bool = False
    solo: bool = False
    keyframes: list[list[float]] = field(default_factory=list)  # [[t, x, y, z], ...]


@dataclass
class ProjectModel:
    tracks: list[TrackState] = field(default_factory=list)
    next_id: int = 0

    def new_track_id(self) -> int:
        tid = self.next_id
        self.next_id += 1
        return tid

    def save(self, path: str):
        data = {
            "next_id": self.next_id,
            "tracks": [
                {
                    "track_id": t.track_id,
                    "filepath": t.filepath,
                    "name": t.name,
                    "color_index": t.color_index,
                    "position": t.position,
                    "priority": t.priority,
                    "muted": t.muted,
                    "solo": t.solo,
                    "keyframes": t.keyframes,
                }
                for t in self.tracks
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "ProjectModel":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        model = cls(next_id=data.get("next_id", 0))
        for td in data.get("tracks", []):
            model.tracks.append(TrackState(**td))
        return model
