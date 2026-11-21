"""One place to decide what kind of place something is.

Each venue gets:
- `category`: the web frontend's fine category (comedy, games, music, culture, bar, food, other)
- `group`: what people browse by (Food, Drinks, Entertainment, Culture, Outdoors)
- a taste tag for ranking and likes (food, nightlife, active, culture, comedy, music, games, …)
"""

from typing import NamedTuple


class Kind(NamedTuple):
    category: str
    group: str
    tag: str
    adult: bool = False


# Google Places (New) types → kind. Order matters: the first match in a place's types wins.
GOOGLE: dict[str, Kind] = {
    "comedy_club": Kind("comedy", "Entertainment", "comedy", adult=True),
    "live_music_venue": Kind("music", "Entertainment", "music"),
    "concert_hall": Kind("music", "Entertainment", "music"),
    "night_club": Kind("music", "Drinks", "club", adult=True),
    "karaoke": Kind("games", "Entertainment", "games"),
    "bowling_alley": Kind("games", "Entertainment", "games"),
    "video_arcade": Kind("games", "Entertainment", "games"),
    "amusement_center": Kind("games", "Entertainment", "games"),
    "movie_theater": Kind("culture", "Entertainment", "film"),
    "performing_arts_theater": Kind("culture", "Entertainment", "theatre"),
    "museum": Kind("culture", "Culture", "culture"),
    "art_gallery": Kind("culture", "Culture", "culture"),
    "park": Kind("other", "Outdoors", "outdoors"),
    "cocktail_bar": Kind("bar", "Drinks", "nightlife", adult=True),
    "wine_bar": Kind("bar", "Drinks", "nightlife", adult=True),
    "pub": Kind("bar", "Drinks", "nightlife", adult=True),
    "bar": Kind("bar", "Drinks", "nightlife", adult=True),
    "dessert_shop": Kind("food", "Food", "food"),
    "cafe": Kind("food", "Food", "food"),
    "restaurant": Kind("food", "Food", "food"),
}

# OpenStreetMap (key, value) → kind
OSM: dict[tuple[str, str], Kind] = {
    ("amenity", "restaurant"): Kind("food", "Food", "food"),
    ("amenity", "cafe"): Kind("food", "Food", "food"),
    ("amenity", "fast_food"): Kind("food", "Food", "food"),
    ("amenity", "bar"): Kind("bar", "Drinks", "nightlife", adult=True),
    ("amenity", "pub"): Kind("bar", "Drinks", "nightlife", adult=True),
    ("amenity", "nightclub"): Kind("music", "Drinks", "club", adult=True),
    ("amenity", "cinema"): Kind("culture", "Entertainment", "film"),
    ("amenity", "theatre"): Kind("culture", "Entertainment", "theatre"),
    ("amenity", "arts_centre"): Kind("culture", "Culture", "culture"),
    ("tourism", "museum"): Kind("culture", "Culture", "culture"),
    ("tourism", "gallery"): Kind("culture", "Culture", "culture"),
    ("leisure", "bowling_alley"): Kind("games", "Entertainment", "games"),
    ("leisure", "amusement_arcade"): Kind("games", "Entertainment", "games"),
    ("leisure", "escape_game"): Kind("games", "Entertainment", "games"),
    ("leisure", "sports_centre"): Kind("games", "Entertainment", "active"),
    ("leisure", "park"): Kind("other", "Outdoors", "outdoors"),
}

# Broad taste families so likes and voice match related places (comedy ↔ music ↔ nightlife, …)
FAMILY = {
    "comedy": "nightlife",
    "music": "nightlife",
    "club": "nightlife",
    "games": "active",
    "film": "culture",
    "theatre": "culture",
}


def google_kind(types: list[str], primary: str = "") -> Kind | None:
    if primary in GOOGLE:
        return GOOGLE[primary]
    return next((GOOGLE[t] for t in GOOGLE if t in types), None)


def tags_for(kind: Kind, outdoors: bool) -> list[str]:
    """Taste tag first (shown as a reason), then its family, then the setting."""
    tags = [kind.tag]
    if kind.tag in FAMILY:
        tags.append(FAMILY[kind.tag])
    tags.append("outdoors" if outdoors or kind.tag == "outdoors" else "indoors")
    return list(dict.fromkeys(tags))
