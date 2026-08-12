"""Editorial city guides — the substance search traffic lands on. One entry per live Buddilio city."""

CITY_GUIDES = {
    "Delhi NCR": {
        "intro": "Delhi goes out in seasons: winter terraces and qawwali courtyards, monsoon supper clubs, "
                 "summer nights that only start after 10pm. The city rewards people who plan — the best tables "
                 "and the best crowds are booked, not stumbled into.",
        "areas": [
            ["Hauz Khas Village", "Lake-facing rooftops and small live-music rooms — the safest bet for a first night out."],
            ["Aerocity", "Hotel bars and late kitchens near the airport; polished, well-staffed, easy to leave from."],
            ["Mehrauli", "Heritage-wall dining and jazz courtyards — Delhi's most romantic-feeling evenings."],
            ["Connaught Place", "Old-school bars, comedy basements and Sunday brunches in the colonial circle."],
        ],
        "when": "Thursday to Saturday, 8:30pm onwards. October to March is peak terrace season.",
        "around": "Metro until ~11pm, then app cabs. Groups usually split one cab per four members.",
        "tip": "Carry a government photo ID — almost every Delhi venue checks age at the door.",
    },
    "Gurugram": {
        "intro": "Gurugram is Delhi NCR's after-work city: glass towers, walkable food courts and a crowd that "
                 "goes out on weeknights because the commute home is five minutes.",
        "areas": [
            ["CyberHub", "Dozens of restaurants and bars in one walkable block — the default post-work meetup."],
            ["Sector 29", "Loud, cheerful and value-driven; big-group nights and open-air seating."],
            ["Golf Course Road", "Quieter cocktail bars and chef-led tasting rooms inside the hotels."],
        ],
        "when": "Wednesday and Thursday nights are surprisingly good here; weekends fill by 9pm.",
        "around": "Rapid Metro plus cabs. Parking is easier than Delhi, so drivers often host the carpool.",
        "tip": "Most CyberHub venues stop entry at 12:30am — start earlier than you would in Delhi.",
    },
    "Noida": {
        "intro": "Noida's social life clusters around its malls, sector markets and a growing set of "
                 "independent cafés — relaxed, affordable and easy to reach from east Delhi.",
        "areas": [
            ["Sector 18", "Atta Market and the malls: cinema, food halls and casual bars in one loop."],
            ["Sector 38A", "The Great India Place strip — bowling, arcades and big-table dinners."],
            ["Sector 32", "Brahmaputra Market's street food, best explored as a group crawl."],
        ],
        "when": "Friday and Saturday evenings; Sunday brunches are the fastest-growing meetup here.",
        "around": "Blue and Aqua line metros cover most sectors; cabs are cheap after hours.",
        "tip": "Noida venues close earlier than Delhi's — plan dinner at 8pm, not 10pm.",
    },
    "Mumbai": {
        "intro": "Mumbai does not need a reason to go out. The city runs late, dresses up, and treats a "
                 "Tuesday gig with the same energy as a Saturday. Distances are the only real obstacle.",
        "areas": [
            ["Bandra West", "Hill Road to Carter Road: listening bars, small-plate kitchens and open mics."],
            ["Lower Parel", "Mill-district rooftops and clubs — the big-night-out choice."],
            ["Colaba & Fort", "Heritage cafés, art walks and old-Bombay bars for a slower evening."],
            ["Juhu", "Beachside sundowners and comedy rooms, best on a weekday when it's calm."],
        ],
        "when": "Any night works. Sundowners start 6:30pm; clubs peak 11pm to 1:30am.",
        "around": "Locals for daylight, cabs after dark. Book venues on the side of town you sleep on.",
        "tip": "Monsoon (June–September) shifts everything indoors — check the venue before you leave.",
    },
    "Bengaluru": {
        "intro": "Bengaluru is India's most conversational night out: microbreweries, listening rooms and "
                 "morning treks that end in filter coffee. The weather makes outdoor seating a year-round default.",
        "areas": [
            ["Indiranagar", "100 Feet Road's breweries, bookshop bars and terrace dinners."],
            ["Koramangala", "Startup-crowd cafés turning into cocktail bars after 9pm."],
            ["Church Street & MG Road", "Live music, old bakeries and the city's best walking crawl."],
            ["Whitefield", "Self-contained brewery and food-hall scene for the east-side crowd."],
        ],
        "when": "Thursday to Saturday. Sunday morning treks and runs are a genuine social scene here.",
        "around": "Purple and Green metro lines plus autos. Traffic decides your neighbourhood, not taste.",
        "tip": "Last call is early by Indian standards — 11:30pm to 1am. Meet at 7:30pm.",
    },
    "Hyderabad": {
        "intro": "Hyderabad pairs old-city food heritage with a new-money lakeside and tech-corridor scene. "
                 "Big tables, generous hosts and a city that eats properly before it drinks.",
        "areas": [
            ["Jubilee Hills", "Rooftop lounges and chef-driven restaurants above the lake."],
            ["Financial District & Gachibowli", "Brewery halls and late kitchens for the tech-corridor crowd."],
            ["Banjara Hills", "Cocktail bars, galleries and the city's most reliable dinner tables."],
        ],
        "when": "Friday and Saturday from 8pm. Ramadan and festival weeks bring exceptional food nights.",
        "around": "Metro to Jubilee Hills Check Post, cabs beyond. Distances are long — carpool.",
        "tip": "Do the Old City biryani crawl as a group before a night out — it's the local ritual.",
    },
    "Pune": {
        "intro": "Pune is a student and studio city that grew up: breweries, cycling groups, live gigs and "
                 "an easy, unpretentious way of meeting new people.",
        "areas": [
            ["Koregaon Park", "Leafy lanes, German Bakery culture, jazz nights and long dinners."],
            ["Baner & Balewadi", "Brewery-and-bowling territory for big groups."],
            ["Kalyani Nagar", "Cocktail bars and rooftop dinners with the calmest crowd in the city."],
        ],
        "when": "Friday and Saturday nights; Sunday morning rides and treks fill up fast.",
        "around": "Autos and cabs. Nothing is more than 30 minutes away outside peak hours.",
        "tip": "Pune is a monsoon city — a weekend Lonavala or Tamhini plan beats a rained-out rooftop.",
    },
    "Goa": {
        "intro": "Goa is two social scenes in one state: the north's late, loud, expat-heavy nights and the "
                 "south's quiet beach-shack dinners. Buddilio groups usually do a weekend of both.",
        "areas": [
            ["Assagao & Anjuna", "Garden restaurants, house parties and the best playlists in India."],
            ["Morjim & Ashwem", "Quieter north beaches, sunset shacks and long lunch tables."],
            ["Panjim (Fontainhas)", "Portuguese lanes, Latin-quarter bars and heritage food walks."],
            ["Palolem & the south", "Slow beach shacks, kayaking mornings and bonfire dinners."],
        ],
        "when": "November to February is peak. Monsoon (June–September) is cheap, green and gloriously empty.",
        "around": "Rent a scooter or bike for daylight; always use a cab at night, never ride after drinks.",
        "tip": "Book beds before parties — accommodation, not tables, is the bottleneck in Goa.",
    },
    "Dubai": {
        "intro": "Dubai's social calendar runs on brunches, sundowners and the desert-cool months between "
                 "October and April. It is one of the easiest cities in the world to arrive in alone and "
                 "leave with a group — as long as you know which strip to be on.",
        "areas": [
            ["Dubai Marina & JBR", "Beach clubs, marina-side terraces and the reliable Friday sundowner."],
            ["Downtown & DIFC", "Fine dining, gallery openings and after-work cocktails among the towers."],
            ["Alserkal Avenue, Al Quoz", "Warehouse galleries, specialty coffee and the city's creative crowd."],
            ["Jumeirah & Kite Beach", "Morning padel, beach runs and casual daytime meetups."],
        ],
        "when": "Thursday to Saturday nights, plus the institution of the Saturday brunch. Peak season October–April.",
        "around": "Metro along Sheikh Zayed Road, cabs everywhere else. Never plan to drive after drinking.",
        "tip": "Dress codes are real in Dubai — smart-casual gets you in almost anywhere; shorts rarely do.",
    },
    "Abu Dhabi": {
        "intro": "Abu Dhabi is Dubai's calmer neighbour: island dining, museums that stay open late and a "
                 "crowd that prefers a long dinner to a loud club.",
        "areas": [
            ["Al Maryah Island", "Waterfront restaurants and hotel bars — the default evening out."],
            ["Saadiyat Island", "Louvre Abu Dhabi, beach clubs and slow Sunday afternoons."],
            ["Yas Island", "Race weekends, arenas and theme-park day plans for big groups."],
            ["The Corniche", "Sunset walks, cycling groups and casual beachside meetups."],
        ],
        "when": "Thursday and Friday evenings; race and concert weekends are the social peaks of the year.",
        "around": "Cabs are cheap and plentiful. Most groups meet at the venue rather than pre-gaming.",
        "tip": "Alcohol is hotel-licensed here — check before you suggest a venue for a non-hotel night.",
    },
    "Singapore": {
        "intro": "Singapore rewards planners: reservations open early, everything is 25 minutes away, and the "
                 "hawker-to-cocktail-bar pipeline is the most efficient night out in Asia.",
        "areas": [
            ["Keong Saik & Chinatown", "Shophouse cocktail bars and modern Asian tasting menus."],
            ["Dempsey Hill", "Leafy, low-key restaurants for a long dinner with new people."],
            ["Marina Bay", "Rooftops, festivals and skyline sundowners for the big-night version."],
            ["Kampong Glam", "Indie bars, record shops and street art around Haji Lane."],
        ],
        "when": "Wednesday to Saturday. Sunday afternoons are for hawker crawls and park runs.",
        "around": "MRT until midnight, then Grab. Nothing needs a car.",
        "tip": "Book two weeks ahead for anything popular — walk-ins are the exception, not the rule.",
    },
    "London": {
        "intro": "London's social life is neighbourhood-shaped: you pick an area, not a venue, and let the "
                 "evening drift between a pub, a small kitchen and something with music in the basement.",
        "areas": [
            ["Soho", "Theatre, small-plate kitchens, jazz cellars and the densest walk-between options in the city."],
            ["Shoreditch & Hackney", "Warehouse bars, supper clubs and Sunday-night gigs east of the City."],
            ["Peckham & Deptford", "Rooftop car parks, community kitchens and the best value in south London."],
            ["Notting Hill & Portobello", "Weekend markets, wine bars and slower daytime meetups."],
        ],
        "when": "Thursday to Saturday, 7pm onwards — Londoners eat and drink early. Summer terraces book out weeks ahead.",
        "around": "Tube until roughly midnight, Night Tube on Fridays and Saturdays, then buses and cabs.",
        "tip": "Most kitchens stop serving at 10pm. Book dinner for 7:30pm and keep the bar for after.",
    },
    "Manchester": {
        "intro": "Manchester is a music city first and a food city second — and both are unusually friendly to "
                 "someone new in town.",
        "areas": [
            ["Northern Quarter", "Independent bars, record shops and small live rooms; the city's social heart."],
            ["Ancoats", "New-wave restaurants and neighbourhood wine bars in the old mills."],
            ["Deansgate & Spinningfields", "Bigger rooms, rooftops and after-work crowds."],
        ],
        "when": "Thursday to Sunday. Match days reshape the whole city — check the fixture before you book.",
        "around": "Trams (Metrolink) and a very walkable centre; cabs for the outer suburbs.",
        "tip": "Buy gig tickets early — Manchester's best nights are announced weeks in advance and sell fast.",
    },
    "New York": {
        "intro": "New York's advantage is density: five plans within ten blocks, and nobody thinks it's odd to "
                 "arrive at a dinner not knowing anyone.",
        "areas": [
            ["Lower East Side", "Bar-hopping, comedy basements and late-night dumplings."],
            ["Williamsburg", "Waterfront sunsets, live music and Sunday-afternoon patios."],
            ["West Village", "Jazz rooms, small Italian kitchens and the city's most walkable date-night grid."],
            ["Chelsea", "Gallery hops on Thursday evenings, then High Line drinks."],
        ],
        "when": "Thursday is the real start of the weekend. Gallery openings cluster on Thursday 6–8pm.",
        "around": "Subway 24/7, plus buses. Cabs make sense only across rivers or after 1am.",
        "tip": "Reserve everything — even a two-person dinner. Cancellations open up around 5pm on the day.",
    },
    "Los Angeles": {
        "intro": "Los Angeles socialising is intentional: you drive somewhere specific, arrive early, and the "
                 "night ends before midnight more often than visitors expect.",
        "areas": [
            ["Silver Lake & Echo Park", "Patio bars, indie venues and the least-industry crowd in town."],
            ["DTLA Arts District", "Breweries, warehouse galleries and rooftop pools."],
            ["West Hollywood", "Sunset Strip institutions and the classic night-out version of LA."],
            ["Venice & Abbot Kinney", "Beach volleyball, sunset runs and casual daytime meetups."],
        ],
        "when": "Thursday to Saturday, 7pm–midnight. Sunday daytime is genuinely social here.",
        "around": "Rideshare is the default; the Metro E and B lines cover a surprising amount of it.",
        "tip": "Traffic doubles your journey after 4pm — pick a neighbourhood you can stay inside all evening.",
    },
    "Miami": {
        "intro": "Miami runs late and outdoors. The city's social scene is split between the beach, the art "
                 "neighbourhoods and a Latin nightlife culture that starts when other cities finish.",
        "areas": [
            ["Wynwood", "Murals, breweries and gallery nights — the most conversational part of town."],
            ["South Beach", "Ocean Drive classics, beach clubs and the big-night version of Miami."],
            ["Little Havana", "Salsa floors, ventanita coffee and Calle Ocho food walks."],
            ["Brickell", "After-work rooftops and skyline dinners for the downtown crowd."],
        ],
        "when": "Thursday to Sunday. Dinner at 9pm, dancing at midnight. Art Basel week (December) is the peak.",
        "around": "Rideshare, plus the free Metromover downtown. Do not plan to park in South Beach.",
        "tip": "Learn two salsa steps before a Little Havana night — everyone dances, nobody minds beginners.",
    },
    "Austin": {
        "intro": "Austin is the friendliest first-night city in America: live music every evening of the week "
                 "and patios built for talking to strangers.",
        "areas": [
            ["Rainey Street", "Converted bungalow bars with food trucks and big shared tables."],
            ["East Sixth", "Dive bars, taquerias and the city's best mid-week live music."],
            ["South Congress", "Rooftops, vintage shopping and Sunday-afternoon patios."],
        ],
        "when": "Any night has live music; Thursday to Saturday are busiest. SXSW and ACL reshape spring and autumn.",
        "around": "Rideshare and scooters; the centre is walkable between Rainey and East Sixth.",
        "tip": "Ask what's playing rather than where to drink — the band decides the night in Austin.",
    },
    "Toronto": {
        "intro": "Toronto is a city of small, distinct strips — pick one and you can walk the whole evening, "
                 "which makes it easy to meet a group you've never met before.",
        "areas": [
            ["Ossington", "Wine bars, listening rooms and the best walk-between block in the city."],
            ["King West", "Bigger rooms, patios and the after-work crowd."],
            ["Kensington Market", "Day drinking, global food stalls and an unhurried Sunday."],
            ["Distillery District", "Heritage brickwork, seasonal markets and winter light nights."],
        ],
        "when": "Thursday to Saturday. Patio season (May–September) is the whole social calendar.",
        "around": "TTC subway and streetcars until 1:30am, then Blue Night buses or rideshare.",
        "tip": "Winter does not cancel plans here — look for venues with a fireplace and book early.",
    },
    "Vancouver": {
        "intro": "Vancouver's social life happens outdoors first: a hike, a seawall run or a beach sunset, "
                 "then dinner. Plans are early, active and easy to join solo.",
        "areas": [
            ["Gastown", "Cobblestone cocktail bars and the city's oldest dining rooms."],
            ["Mount Pleasant & Main Street", "Breweries, small kitchens and the most local crowd."],
            ["Kitsilano", "Beach sunsets, volleyball and morning coffee groups."],
            ["Yaletown", "Waterfront patios and after-work drinks downtown."],
        ],
        "when": "Thursday to Saturday evenings; weekend mornings are for mountains and the seawall.",
        "around": "SkyTrain and SeaBus, plus a genuinely usable bike network.",
        "tip": "Bring a layer — even in July the temperature drops the moment the sun goes behind the mountains.",
    },
    "Sydney": {
        "intro": "Sydney's social year is organised around water and daylight: swims, harbour picnics and "
                 "long lunches that quietly turn into evenings.",
        "areas": [
            ["Surry Hills", "Small bars, terrace kitchens and the city's most reliable dinner crowd."],
            ["Newtown", "Live music, late food and the least formal night out in Sydney."],
            ["Circular Quay & The Rocks", "Harbour views, historic pubs and festival nights."],
            ["Bondi & the coast", "Sunrise swims, coastal walks and beer-garden afternoons."],
        ],
        "when": "Thursday to Sunday. Summer (December–February) is peak; Sunday afternoon is a real social slot.",
        "around": "Trains, ferries and light rail; ferries are the nicest way to arrive anywhere.",
        "tip": "Sydney kitchens close early — a 6:30pm booking is normal, not antisocial.",
    },
    "Melbourne": {
        "intro": "Melbourne hides its social life in laneways and upstairs rooms. Locals will happily walk you "
                 "through four venues in one night, none of which have a sign.",
        "areas": [
            ["Fitzroy & Collingwood", "Brunswick Street bars, live rooms and vintage shopping."],
            ["CBD laneways", "Hidden rooftops, wine bars and the coffee culture that started it all."],
            ["St Kilda", "Beachfront sunsets, cake shops and Sunday markets."],
        ],
        "when": "Wednesday to Saturday. Winter is indoor-bar season and the city genuinely thrives in it.",
        "around": "Trams (free in the CBD zone), trains and a compact, walkable centre.",
        "tip": "Four seasons in one day is not a joke — always carry a jacket, whatever the forecast says.",
    },
    "Berlin": {
        "intro": "Berlin's nights are long and unhurried. Dinner at 9pm, a bar at midnight, and nobody checks "
                 "the time. It is also the easiest European city to show up to alone.",
        "areas": [
            ["Kreuzberg", "Canal-side bars, Turkish markets and the densest night-out grid in Berlin."],
            ["Neukölln", "Neighbourhood wine bars, courtyards and a young international crowd."],
            ["Prenzlauer Berg", "Slow brunches, playgrounds-turned-beer-gardens and calm evenings."],
            ["Mitte", "Galleries, cocktail bars and after-work dinners in the centre."],
        ],
        "when": "Thursday to Sunday. Clubs start after 1am; sunset beer gardens run all summer.",
        "around": "U-Bahn and S-Bahn run all night on weekends. Cash is still king in many bars.",
        "tip": "Book nothing loudly and photograph nobody in clubs — Berlin's door culture takes both seriously.",
    },
    "Barcelona": {
        "intro": "Barcelona eats late and lives outside. Vermouth at 1pm, dinner at 10pm, and a beach that is "
                 "twenty minutes from every neighbourhood in the city.",
        "areas": [
            ["Gothic Quarter", "Medieval lanes, tapas counters and small live-music rooms."],
            ["El Born", "Design shops, wine bars and the best dinner-to-drinks walk in the city."],
            ["Gràcia", "Village squares, terrace beers and a local crowd that talks to strangers."],
            ["Barceloneta", "Beach volleyball, chiringuitos and sunset swims after work."],
        ],
        "when": "Thursday to Saturday. Dinner at 9:30pm; nights out start after midnight. Festes de Gràcia (August) is the peak.",
        "around": "Metro until midnight (all night on Saturdays), plus a flat, very cycleable city.",
        "tip": "Watch your bag in the Gothic Quarter and Barceloneta — pickpocketing is the city's one real risk.",
    },
    "Madrid": {
        "intro": "Madrid is the most social capital in Europe: it eats late, sleeps little, and treats a "
                 "Tuesday terrace as a legitimate plan.",
        "areas": [
            ["Malasaña", "Indie bars, record shops and the city's youngest night-out crowd."],
            ["La Latina", "Sunday vermouth, tapas crawls and the Rastro market afterwards."],
            ["Chueca", "Cocktail bars, terraces and Madrid's most welcoming nightlife."],
            ["Salamanca", "Smarter dining rooms and rooftop drinks for a dressed-up evening."],
        ],
        "when": "Thursday to Sunday. Dinner at 10pm, bars until 3am. Sunday vermouth in La Latina is an institution.",
        "around": "Metro until 1:30am, night buses after. The centre is entirely walkable.",
        "tip": "Never arrive at 8pm expecting a crowd — Madrid fills up two hours later than most cities.",
    },
    "Paris": {
        "intro": "Paris socialises in small rooms and on café terraces. Groups are intimate, dinners are long, "
                 "and the best evenings are built around one good table.",
        "areas": [
            ["Le Marais", "Wine bars, galleries and the most walkable evening in the city."],
            ["Canal Saint-Martin", "Canal-side apéro, natural wine and a young local crowd."],
            ["Pigalle & South Pigalle", "Cocktail bars and live music below Montmartre."],
            ["Saint-Germain-des-Prés", "Jazz cellars, brasseries and classic Paris nights."],
        ],
        "when": "Wednesday to Saturday. Apéro at 7pm, dinner at 9pm. August empties the city — check before planning.",
        "around": "Métro until ~1:15am (2:15am on weekends), then Noctilien buses or Vélib bikes.",
        "tip": "Reserve dinner; Parisian kitchens are small and walk-ins on a Friday almost never work.",
    },
    "Bangkok": {
        "intro": "Bangkok is the most generous food city on the planet and its nights layer easily: street "
                 "dinner, rooftop drink, late noodles. Nothing needs to be expensive to be excellent.",
        "areas": [
            ["Thonglor & Ekkamai", "Speakeasies, izakayas and the city's most stylish crowd."],
            ["Ari", "Neighbourhood cafés and small kitchens — the calmest way to meet people."],
            ["Yaowarat (Chinatown)", "Street-food crawls after dark, then upstairs cocktail bars."],
            ["Riverside", "Sunset boats, rooftop views and slower evenings by the Chao Phraya."],
        ],
        "when": "Any night. Rooftops open at 5pm; street food peaks 7–11pm. Cool season is November–February.",
        "around": "BTS Skytrain and MRT until midnight, then metered taxis and river boats by day.",
        "tip": "Do Chinatown as a walking crawl, not a single restaurant — that's where the night actually happens.",
    },
    "Tokyo": {
        "intro": "Tokyo is a city of tiny rooms: six seats, one chef, one bartender who remembers you. Going "
                 "out here is about sequence — three small places beat one big one.",
        "areas": [
            ["Shibuya", "Music bars, izakaya alleys and the easiest first night out."],
            ["Shinjuku (Golden Gai & Omoide Yokocho)", "Six-seat bars and yakitori under the tracks."],
            ["Nakameguro", "Riverside cafés, listening bars and a slower, local evening."],
            ["Ginza", "Cocktail temples and counter dining for a dressed-up night."],
        ],
        "when": "Friday and Saturday, from 6:30pm. Cherry blossom (late March) and autumn leaves (November) are the social peaks.",
        "around": "Trains stop around midnight — either leave by 11:45pm or stay out until 5am. Both are normal.",
        "tip": "Many bars have a small seating charge and cash-only policy. Carry ¥5,000 in notes.",
    },
}


def guide_for(city: str) -> dict:
    return CITY_GUIDES.get((city or "").strip(), {})
