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
    booking: bool = (
        False  # shows, gigs, comedy, cinema: you book a time; everything else is walk-in
    )


# Google Places (New) types → kind. Order matters: the first match in a place's types wins.
GOOGLE: dict[str, Kind] = {
    "comedy_club": Kind("comedy", "Entertainment", "comedy", adult=True, booking=True),
    "live_music_venue": Kind("music", "Entertainment", "music", booking=True),
    "concert_hall": Kind("music", "Entertainment", "music", booking=True),
    "night_club": Kind("music", "Drinks", "club", adult=True),
    "karaoke": Kind("games", "Entertainment", "games"),
    "bowling_alley": Kind("games", "Entertainment", "games"),
    "video_arcade": Kind("games", "Entertainment", "games"),
    "amusement_center": Kind("games", "Entertainment", "games"),
    "movie_theater": Kind("culture", "Entertainment", "film", booking=True),
    "performing_arts_theater": Kind("culture", "Entertainment", "theatre", booking=True),
    "museum": Kind("culture", "Culture", "culture"),
    "art_gallery": Kind("culture", "Culture", "culture"),
    "park": Kind("other", "Outdoors", "outdoors"),
    "city_park": Kind("other", "Outdoors", "outdoors"),
    "opera_house": Kind("music", "Entertainment", "music", booking=True),
    "event_venue": Kind("music", "Entertainment", "music", booking=True),
    "miniature_golf_course": Kind("games", "Entertainment", "games"),
    "casino": Kind("games", "Entertainment", "games", adult=True),
    "cultural_center": Kind("culture", "Culture", "culture"),
    "scenic_spot": Kind("culture", "Culture", "culture", booking=True),
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
    ("amenity", "cinema"): Kind("culture", "Entertainment", "film", booking=True),
    ("amenity", "theatre"): Kind("culture", "Entertainment", "theatre", booking=True),
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


FOOD = Kind("food", "Food", "food")
DRINKS = Kind("bar", "Drinks", "nightlife", adult=True)
# Things to do that Google often files under "bar" (Puttshack, Flight Club, Lucky Voice): if any
# of these is in a place's types, it's Entertainment whatever its primary type says.
DOING_FIRST = (
    "comedy_club",
    "live_music_venue",
    "karaoke",
    "bowling_alley",
    "video_arcade",
    "miniature_golf_course",
    "amusement_center",
)
# Not a night out: schools, hostels, and fast-food chains Google types as restaurants
NOT_A_PLAN = {"university", "school", "primary_school", "secondary_school", "hostel", "lodging"}
CHAIN_FOOD = {
    "fast_food_restaurant",
    "chicken_restaurant",
    "chicken_wings_restaurant",
    "hamburger_restaurant",
}


def google_kind(types: list[str], primary: str = "") -> Kind | None:
    """Google's primary type decides, with a few corrections from auditing real London results."""
    if NOT_A_PLAN & set(types) or primary in CHAIN_FOOD:
        return None
    doing = next((t for t in DOING_FIRST if t in types), None)
    if doing:
        return GOOGLE[doing]
    if primary in GOOGLE:
        return GOOGLE[primary]
    # Google has dozens of cuisine types (indian_restaurant, steak_house, food_court, …)
    if primary.endswith("_restaurant") or primary in {
        "steak_house",
        "food_court",
        "brunch_restaurant",
    }:
        return FOOD
    if primary.endswith(("_pub", "_bar")) or primary == "bar_and_grill":
        return DRINKS
    if primary.endswith("_museum"):
        return GOOGLE["museum"]
    if primary.endswith("_park"):
        return GOOGLE["park"]
    if primary:
        return None  # a known-but-unmapped primary type (store, market, tourist_attraction, …)
    # No primary type at all: first match in the types list (a pub that serves food stays a pub)
    return next((GOOGLE[t] for t in GOOGLE if t in types), None)


def tags_for(kind: Kind, outdoors: bool) -> list[str]:
    """Taste tag first (shown as a reason), then its family, then the setting."""
    tags = [kind.tag]
    if kind.tag in FAMILY:
        tags.append(FAMILY[kind.tag])
    tags.append("outdoors" if outdoors or kind.tag == "outdoors" else "indoors")
    return list(dict.fromkeys(tags))
