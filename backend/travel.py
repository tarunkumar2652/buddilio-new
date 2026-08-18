"""Solo travel: trip listings members join for free, and paid guides/cooks/porters who register once."""

PROVIDER_ROLES = [
    {"key": "guide", "label": "Local guide"},
    {"key": "trek_guide", "label": "Trek / mountain guide"},
    {"key": "cook", "label": "Cook"},
    {"key": "porter", "label": "Porter"},
    {"key": "driver", "label": "Driver"},
    {"key": "photographer", "label": "Photographer"},
    {"key": "gear", "label": "Camping gear"},
    {"key": "translator", "label": "Translator"},
    {"key": "instructor", "label": "Activity instructor"},
]

TRIP_ACTIVITIES = ["Trekking", "Backpacking", "Safari", "Beach", "City break", "Road trip",
                   "Diving", "Skiing", "Pilgrimage", "Food trail", "Camping", "Cycling"]

TRAVEL_TERMS = ("Trips are member-organised — Buddilio doesn't run them. Meet in public, share your plan with "
                "someone at home, and never hand over documents or cash before you arrive. Provider bookings "
                "are paid through Buddilio; anything agreed off-platform isn't covered.")
