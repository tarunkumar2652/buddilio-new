"""Seeds/refreshes Buddilio's public policy and information pages.

Run: python -m scripts.seed_policies   (from /app/backend)
Idempotent: pages are matched on slug and rewritten, keeping their id and version history.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv("/app/backend/.env")

ENTITY = {"name": "Buddilio", "address": "Gurugram-122505, Haryana, India",
          "email": "info@buddilio.com", "msme": "UDYAM-HR-05-0203611",
          "grievance": "Manish Kumar", "jurisdiction": "Gurugram, Haryana"}

FOOTER_NOTE = ("Buddilio is a social discovery and experience platform for adults aged 21+. Buddilio is not a "
               "dating or matchmaking platform. User interactions, third-party services, events and experiences "
               "may involve independent individuals or vendors. Please use the platform responsibly and review "
               "our Safety Centre, Community Guidelines, Terms &amp; Conditions and applicable purchase policies "
               "before using our services.")


def ul(items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def ol(items):
    return "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def p(*paras):
    return "".join(f"<p>{x}</p>" for x in paras)


def h3(t):
    return f"<h3>{t}</h3>"


def link(label, href):
    return f'<a href="{href}">{label}</a>'


RELATED = {
    "terms": [("Privacy Policy", "/p/privacy"), ("Cancellation &amp; Refund Policy", "/p/refund"),
              ("Community Guidelines", "/p/guidelines"), ("Safety Centre", "/safety")],
    "privacy": [("Cookie Policy", "/p/cookies"), ("Terms &amp; Conditions", "/p/terms")],
    "faq": [("Safety Centre", "/safety"), ("Cancellation &amp; Refund Policy", "/p/refund")],
    "refund": [("Terms &amp; Conditions", "/p/terms"), ("Contact Support", "/p/contact")],
    "vendor-terms": [("Vendor Agreement", "/vendor/agreement"), ("Terms &amp; Conditions", "/p/terms")],
    "guidelines": [("Safety Centre", "/safety"), ("Report a Concern", "/p/report")],
    "safety": [("Community Guidelines", "/p/guidelines"), ("Report a Concern", "/p/report")],
    "about": [("How It Works", "/p/how-it-works"), ("FAQ", "/p/faq")],
    "how-it-works": [("FAQ", "/p/faq"), ("Membership", "/membership")],
    "contact": [("FAQ", "/p/faq"), ("Report a Concern", "/p/report")],
    "report": [("Safety Centre", "/safety"), ("Community Guidelines", "/p/guidelines")],
    "cookies": [("Privacy Policy", "/p/privacy")],
    "grievance": [("Contact Us", "/p/contact"), ("Terms &amp; Conditions", "/p/terms")],
    "cities": [("Events", "/events"), ("Companions", "/companions")],
    "insights": [("Events", "/events")],
    "trust": [("Safety Centre", "/safety"), ("Community Guidelines", "/p/guidelines")],
}


def blocks(*items):
    return [b for b in items if b]


def text(heading, body):
    return {"type": "richtext", "heading": heading, "text": body}


def faq(heading, pairs):
    return {"type": "faq", "heading": heading, "items": [f"{q}|{a}" for q, a in pairs]}


def related_block(slug):
    pairs = RELATED.get(slug, [])
    if not pairs:
        return None
    return text("Related pages", ul([link(l, h) for l, h in pairs]))


PAGES = [
    # ---------------- About ----------------
    dict(slug="about", title="About Buddilio",
         seo_title="About Buddilio | Social Discovery & Experiences",
         seo_description="Learn about Buddilio, a social discovery and experience platform helping adults "
                         "discover companions, events, activities and experiences.",
         nav_footer_group="Buddilio", nav_label="About Us", order=1,
         content=p("<b>Find your people for every experience.</b>",
                   "Buddilio is a social discovery and experience platform designed to help adults discover "
                   "people, events, activities and experiences that make social life easier, more comfortable "
                   "and more meaningful.",
                   "Whether you want someone to join you for a dinner, attend an event, explore a new place, "
                   "enjoy an activity, travel, celebrate an occasion or simply share an experience, Buddilio "
                   "helps make social connections more accessible."),
         blocks=blocks(
             text("What Buddilio is", p("Buddilio brings together:") + ul([
                 "Social discovery", "Companionship", "Events", "Activities", "Experiences",
                 "Lifestyle opportunities", "Communities", "Local experiences"])
                 + p("The platform allows users to discover opportunities and connect with people who may "
                     "share similar interests.")),
             text("Is Buddilio a dating app?",
                  p("<b>No.</b> Buddilio is not a dating or matchmaking platform. Buddilio focuses on social "
                    "companionship, experiences, events and shared activities. Users may meet people through "
                    "Buddilio, but the platform does not promise romantic relationships or dating outcomes.")),
             text("Why we built Buddilio",
                  p("Going to an event alone can sometimes feel uncomfortable.") + ul([
                      "You may want to attend a wedding but not know anyone.",
                      "You may want to try a new restaurant but prefer company.",
                      "You may want to attend a party, activity, trip or social experience but don't want to go alone."])
                  + p("Buddilio exists to make those experiences easier to access.")),
             text("Our approach", p("We believe social experiences should be:") + ul([
                 "Comfortable", "Inclusive", "Transparent", "Respectful", "Safe", "Accessible"])
                 + p("We encourage users to meet responsibly, communicate respectfully and make informed decisions.")),
             text("Our community",
                  p("Buddilio is designed for adults aged 21 years and above. Everyone using Buddilio is "
                    "expected to respect other members and follow our Terms &amp; Conditions, Community "
                    "Guidelines and Safety Standards.")),
             text("Our vision",
                  p("To become a trusted global platform for discovering people, experiences and meaningful "
                    "social moments.")),
             related_block("about"))),

    # ---------------- How it works ----------------
    dict(slug="how-it-works", title="How Buddilio Works",
         seo_title="How Buddilio Works | Social Discovery & Experiences",
         seo_description="See how Buddilio works — create an account, discover people and experiences, "
                         "connect, confirm and enjoy responsibly.",
         nav_footer_group="Buddilio", nav_label="How It Works", order=2,
         content=p("Buddilio makes discovering social experiences and companions simple."),
         blocks=blocks(
             text("Step 1 — Create your account",
                  p("Create your Buddilio account with accurate information. You must be at least 21 years old.")),
             text("Step 2 — Discover", p("Explore:") + ul([
                 "People", "Events", "Activities", "Experiences", "Dining", "Parties", "Travel",
                 "Social gatherings", "Lifestyle experiences"])
                 + p("Availability may vary by city and category.")),
             text("Step 3 — Connect", p("Depending on the feature, you may:") + ul([
                 "View profiles", "Send connection requests", "Communicate", "Join an event",
                 "Book an experience", "Request companionship"])),
             text("Step 4 — Confirm", p("Review the applicable:") + ul([
                 "Price", "Terms", "Cancellation policy", "Event details", "Vendor information"])
                 + p("before completing a transaction.")),
             text("Step 5 — Enjoy responsibly",
                  p("Meet in appropriate public or designated locations and follow Buddilio's "
                    + link("Safety Centre", "/safety") + " and "
                    + link("Community Guidelines", "/p/guidelines") + ".")),
             related_block("how-it-works"))),

    # ---------------- FAQ ----------------
    dict(slug="faq", title="Frequently Asked Questions",
         seo_title="Buddilio FAQ | Frequently Asked Questions",
         seo_description="Find answers about Buddilio memberships, companions, events, bookings, safety, "
                         "payments, cancellations and how the platform works.",
         nav_footer_group="Buddilio", nav_label="FAQ", order=3,
         content=p("Everything members ask most often. Still stuck? Write to "
                   f"<a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>."),
         blocks=blocks(
             faq("About the platform", [
                 ("Is Buddilio a dating app?",
                  "No. Buddilio is a social discovery and experience platform designed to help adults find "
                  "companions and discover events, activities and experiences. It is not a dating or "
                  "matchmaking platform."),
                 ("Who can use Buddilio?",
                  "Buddilio is available to adults aged 21 years and above. You may be required to provide "
                  "your date of birth during registration."),
                 ("Do I need a membership?",
                  "Not necessarily. Users may browse Buddilio and access certain free features without a paid "
                  "membership. Some features, experiences, events or premium services may require payment."),
             ]),
             faq("Companions and experiences", [
                 ("Can I use Buddilio to find a companion for an event?",
                  "Yes. Buddilio is designed to help users discover companions and social experiences, subject "
                  "to availability and the applicable service terms."),
                 ("Can I find companions for weddings or parties?",
                  "Yes. Depending on availability, Buddilio may offer companionship and experiences connected "
                  "with weddings, parties, dining, events, social gatherings, activities, travel and lifestyle "
                  "experiences."),
                 ("Is companionship romantic?",
                  "Not necessarily. Buddilio is not a dating or matchmaking service. Users are expected to "
                  "maintain respectful and appropriate boundaries."),
                 ("Are Buddilio users verified?",
                  "Buddilio may use verification mechanisms depending on the feature, service and "
                  "availability. Verification does not mean that Buddilio guarantees a person's identity, "
                  "character, background or behaviour. Users should always exercise reasonable caution."),
             ]),
             faq("Payments, memberships and refunds", [
                 ("Can I cancel a membership?",
                  "Cancellation and refund eligibility depends on the applicable membership or purchase terms. "
                  "Please review the Cancellation &amp; Refund Policy before purchasing."),
                 ("Do memberships automatically renew?",
                  "Membership renewal will occur only where the applicable membership terms clearly provide "
                  "for renewal and the user has authorised the applicable renewal mechanism. Users should "
                  "review their membership status and renewal terms."),
                 ("Can I get a refund?",
                  "Refund eligibility depends on the product, membership, event, booking and applicable "
                  "cancellation policy. Some purchases may be non-refundable. Please review the applicable "
                  "cancellation terms before payment."),
             ]),
             faq("Safety and privacy", [
                 ("Can I report another user?",
                  "Yes. Users can report inappropriate, unsafe, abusive, fraudulent or suspicious behaviour "
                  "through the available reporting mechanism or by contacting Buddilio Support."),
                 ("What should I do if I feel unsafe?",
                  "Move to a safe or public location and contact appropriate local emergency services where "
                  "necessary. You should also report the incident to Buddilio."),
                 ("Can I share my financial information with another user?",
                  "No. Never share bank passwords, OTPs, card PINs, internet banking credentials, payment "
                  "passwords or sensitive financial information with another user. Buddilio will not ask you "
                  "to provide your banking password or payment PIN to another user."),
                 ("Can I meet someone privately?",
                  "Users make their own decisions about meetings. Buddilio strongly recommends first meetings "
                  "take place in public and populated locations."),
                 ("Can I delete my account?",
                  "Where account deletion is available, users may request deletion through the applicable "
                  "account controls or by contacting Buddilio. Certain information may need to be retained "
                  "where required by law, legitimate business requirements, dispute resolution or security "
                  "purposes."),
             ]),
             related_block("faq"))),

    # ---------------- Community guidelines ----------------
    dict(slug="guidelines", title="Community Guidelines",
         seo_title="Buddilio Community Guidelines | Safe & Respectful Community",
         seo_description="Read Buddilio's Community Guidelines covering respectful behaviour, privacy, "
                         "harassment, scams, safety and prohibited activities.",
         nav_footer_group="Safety & Trust", nav_label="Community Guidelines", order=2,
         content=p("Buddilio is built around respectful social interaction. Everyone using Buddilio must help "
                   "maintain a safe and welcoming community."),
         blocks=blocks(
             text("1. Be respectful", p("Treat other members with dignity. Do not engage in:") + ul([
                 "Harassment", "Bullying", "Threats", "Intimidation", "Abuse", "Humiliation",
                 "Unwanted repeated contact"])),
             text("2. Be honest", p("Do not:") + ul([
                 "Impersonate another person", "Use fake identities",
                 "Provide intentionally misleading information", "Misrepresent your age",
                 "Misrepresent services", "Create fraudulent profiles"])),
             text("3. Respect boundaries",
                  p("Consent and personal boundaries must always be respected. Do not pressure another person to:")
                  + ul(["Meet", "Continue communication", "Share personal information", "Share photographs",
                        "Engage in romantic or sexual activity", "Send money", "Provide services"])),
             text("4. No financial manipulation", p("Do not use Buddilio to:") + ul([
                 "Request money through deception", "Run scams", "Conduct fraudulent transactions",
                 "Obtain financial credentials", "Manipulate another user financially"])),
             text("5. No harassment or hate",
                  p("Content targeting individuals or groups through hateful, abusive or discriminatory conduct "
                    "is prohibited.")),
             text("6. No illegal activities",
                  p("Buddilio may not be used for activities that violate applicable law.")),
             text("7. No sexual exploitation",
                  p("Buddilio does not permit sexual exploitation, coercion, trafficking or other abusive "
                    "sexual conduct. The platform is not intended to facilitate prostitution or illegal sexual "
                    "services.")),
             text("8. No spam", p("Do not:") + ul([
                 "Send unsolicited promotional messages", "Mass-message users", "Promote fraudulent offers",
                 "Distribute malicious links", "Repeatedly contact users who have declined communication"])),
             text("9. Respect privacy", p("Do not publish or share another person's:") + ul([
                 "Phone number", "Address", "Private photographs", "Financial information",
                 "Identification documents", "Private conversations"])
                 + p("without appropriate authorisation.")),
             text("10. Report problems",
                  p("If you see content or behaviour that violates these guidelines, "
                    + link("report it to Buddilio", "/p/report") + ".")),
             text("Enforcement", p("Buddilio may:") + ul([
                 "Warn users", "Remove content", "Restrict features", "Suspend accounts", "Remove accounts",
                 "Cancel bookings", "Take other appropriate action"])
                 + p("depending on the circumstances. Serious violations may result in immediate account "
                     "termination.")),
             related_block("guidelines"))),

    # ---------------- Safety centre ----------------
    dict(slug="safety", title="Buddilio Safety Centre",
         seo_title="Buddilio Safety Centre | Stay Safe While Meeting People",
         seo_description="Learn how to use Buddilio safely, protect your personal information, meet "
                         "responsibly and report suspicious or unsafe behaviour.",
         nav_footer_group="Safety & Trust", nav_label="Safety Centre", order=1,
         content=p("<b>Your safety matters.</b>",
                   "Buddilio is designed to make social discovery and experiences easier, but no online "
                   "platform can guarantee that every interaction or meeting will be safe. Please use good "
                   "judgment and take reasonable precautions."),
         blocks=blocks(
             text("Meet in public", p("For first meetings, choose:") + ul([
                 "Cafés", "Restaurants", "Shopping centres", "Event venues", "Public places",
                 "Other populated locations"]) + p("Avoid isolated locations for first meetings.")),
             text("Tell someone you trust", p("Let a friend or family member know:") + ul([
                 "Who you are meeting", "Where you are going",
                 "Approximately when you expect to return"])),
             text("Control your personal information", p("Do not unnecessarily share:") + ul([
                 "Home address", "Workplace address", "Financial information", "Passwords", "OTPs",
                 "Identity documents", "Private photographs"])),
             text("Protect your money",
                  p("Never send money to another user simply because they claim to need urgent financial "
                    "assistance. Be especially cautious about:") + ul([
                      "Investment requests", "Emergency-money requests", "Loan requests",
                      "Gift-card requests", "Payment links", "Requests for OTPs",
                      "Requests for banking credentials"])),
             text("During a meeting",
                  p("If something feels wrong, leave. You do not owe another person continued interaction. "
                    "Move to a public location and contact someone you trust.")),
             text("Emergency situations",
                  p("If you believe you are in immediate danger, contact the appropriate emergency services in "
                    "your location. Buddilio is not an emergency-response service.")),
             text("Report suspicious behaviour", p("Report:") + ul([
                 "Fraud", "Harassment", "Threats", "Fake profiles", "Financial scams", "Unsafe behaviour",
                 "Abuse", "Impersonation", "Suspicious activity"])
                 + p(link("Report a concern", "/p/report") + " at any time.")),
             text("Important reminder",
                  p("Verification or a profile badge does not guarantee that a person is safe, trustworthy or "
                    "suitable. Always use your own judgment.")),
             related_block("safety"))),

    # ---------------- Report a concern ----------------
    dict(slug="report", title="Report a Concern",
         seo_title="Report a Concern | Buddilio Safety",
         seo_description="Report harassment, abuse, fraud, scams, fake profiles or unsafe behaviour to the "
                         "Buddilio safety team.",
         nav_footer_group="Safety & Trust", nav_label="Report a Concern", order=3,
         content=p("If you experience or observe any of the following, please report it to Buddilio.")
                 + ul(["Harassment", "Abuse", "Fraud", "Scams", "Threats", "Fake profiles",
                       "Unsafe behaviour", "Inappropriate content", "Privacy violations",
                       "Suspicious activity"]),
         blocks=blocks(
             text("Information to include", p("Where possible, provide:") + ul([
                 "Your name", "Registered email", "Username or profile", "Description of the issue",
                 "Date and time", "Relevant screenshots", "Booking or event information",
                 "Other information that may help us investigate"])
                 + p("Do not include unnecessary sensitive information. Buddilio may investigate reports and "
                     "take appropriate action.")),
             text("How to reach the safety team",
                  p("Use the in-app report option on any profile, event or message, or email "
                    f"<a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>. For urgent physical safety "
                    "situations, contact local emergency services first.")),
             related_block("report"))),

    # ---------------- Privacy ----------------
    dict(slug="privacy", title="Privacy Policy",
         seo_title="Buddilio Privacy Policy | How We Protect Your Information",
         seo_description="Read Buddilio's Privacy Policy to understand what information we collect, how we "
                         "use it, how we protect it and your available privacy rights.",
         nav_footer_group="Legal", nav_label="Privacy Policy", order=1,
         content=p(f"{ENTITY['name']} (\"Buddilio\", \"we\", \"us\" or \"our\") respects your privacy and is "
                   "committed to protecting your personal information.",
                   "Buddilio is a social discovery and experience platform that helps adults discover events, "
                   "activities, experiences and companions with shared interests.",
                   "This Privacy Policy explains what information we collect, why we collect it, how we use "
                   "it, when we share it, how long we retain it and the rights available to you."),
         blocks=blocks(
             text("1. Information we collect",
                  h3("Account information") + ul(["Name", "Email address", "Mobile number", "Date of birth",
                                                  "Login credentials", "Profile information"])
                  + h3("Profile information") + ul(["Profile photograph", "Interests", "Preferences",
                                                    "Location information you choose to provide", "Biography",
                                                    "Experience preferences"])
                  + h3("Transaction information") + ul(["Membership purchases", "Event bookings",
                                                        "Payment status", "Transaction references",
                                                        "Refund information"])
                  + p("Payment card details may be processed by third-party payment providers and may not be "
                      "stored directly by Buddilio.")
                  + h3("Communications")
                  + p("We may process communications necessary to provide the service, support users, prevent "
                      "abuse and comply with applicable law.")
                  + h3("Technical information") + ul(["IP address", "Browser information",
                                                      "Device information", "Operating system",
                                                      "Usage information", "Cookies and similar technologies"])),
             text("2. How we use information", p("We may use information to:") + ul([
                 "Create and manage accounts", "Provide platform services", "Enable social discovery",
                 "Facilitate bookings", "Process payments", "Provide customer support", "Improve the platform",
                 "Prevent fraud", "Detect abuse", "Maintain platform security",
                 "Communicate important updates", "Personalise experiences",
                 "Comply with legal obligations"])),
             text("3. How we share information", p("We may share information with:") + ul([
                 "Service providers", "Payment processors", "Vendors where necessary to fulfil bookings",
                 "Technology providers", "Security and fraud-prevention providers", "Professional advisers",
                 "Authorities where legally required"])
                 + p("We do not sell personal information simply for the purpose of selling personal data to "
                     "third parties.")),
             text("4. Public profile information",
                  p("Information that you choose to make publicly visible on your Buddilio profile may be "
                    "visible to other users. Do not publish information that you do not want other users to see.")),
             text("5. Messages and safety",
                  p("Buddilio may use appropriate technical and moderation measures to detect abuse, fraud, "
                    "threats or violations of our policies. Where legally permitted and reasonably necessary, "
                    "communications may be reviewed or processed for safety, security, moderation and legal "
                    "compliance.")),
             text("6. Cookies", p("Buddilio may use cookies and similar technologies to:") + ul([
                 "Maintain login sessions", "Remember preferences", "Improve functionality",
                 "Understand usage", "Improve security", "Support analytics"])
                 + p("Users may control cookies through browser settings, although disabling certain cookies "
                     "may affect functionality. See our " + link("Cookie Policy", "/p/cookies") + ".")),
             text("7. Data security",
                  p("We use reasonable technical and organisational measures designed to protect information. "
                    "However, no internet-based system can guarantee absolute security.")),
             text("8. Data retention", p("We retain information for as long as reasonably necessary for:") + ul([
                 "Providing services", "Legal compliance", "Security", "Fraud prevention",
                 "Dispute resolution", "Financial and accounting requirements",
                 "Legitimate business purposes"])),
             text("9. Your rights",
                  p("Depending on applicable law, you may have rights relating to access, correction, "
                    "deletion, withdrawal of consent, grievance redressal and other applicable privacy rights.")
                  + p(f"Requests may be submitted to <a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>. "
                      f"Grievance Officer: {ENTITY['grievance']}, {ENTITY['name']}, {ENTITY['address']}.")),
             text("10. Children's privacy",
                  p("Buddilio is intended for adults aged 21 years and above. We do not knowingly provide "
                    "accounts to persons below the applicable minimum age.")),
             text("11. Changes",
                  p("We may update this Privacy Policy periodically. The updated version will be published on "
                    "this page with a revised \"Last updated\" date.")),
             related_block("privacy"))),

    # ---------------- Terms ----------------
    dict(slug="terms", title="Terms & Conditions",
         seo_title="Buddilio Terms & Conditions",
         seo_description="Read the Buddilio Terms & Conditions governing accounts, memberships, events, "
                         "bookings, user conduct, payments and platform use.",
         nav_footer_group="Legal", nav_label="Terms & Conditions", order=2,
         content=p("Welcome to Buddilio. By accessing or using Buddilio, you agree to these Terms &amp; "
                   "Conditions. If you do not agree with these Terms, do not use the platform."),
         blocks=blocks(
             text("1. Eligibility",
                  p("You must be at least 21 years old to use Buddilio. By registering, you confirm that you "
                    "meet this requirement.")),
             text("2. Buddilio is not a dating platform",
                  p("Buddilio is a social discovery, companionship and experience platform. It is not a dating "
                    "or matchmaking service. Buddilio does not guarantee friendships, companionship, romantic "
                    "relationships or any particular outcome.")),
             text("3. User accounts",
                  p("You must provide accurate information. You are responsible for your account, your login "
                    "credentials and activity conducted through your account. Do not share your account "
                    "credentials.")),
             text("4. Acceptable use", p("You agree not to use Buddilio for:") + ul([
                 "Fraud", "Harassment", "Abuse", "Threats", "Illegal activities", "Impersonation", "Scams",
                 "Spam", "Financial manipulation", "Sexual exploitation", "Privacy violations",
                 "Malicious activity"])),
             text("5. User interactions",
                  p("Users are responsible for their interactions with other users. Buddilio does not "
                    "guarantee the identity, intentions, background, behaviour or safety of another user. Use "
                    "reasonable caution.")),
             text("6. Events and experiences",
                  p("Events and experiences may be provided by independent vendors, organisers or service "
                    "providers. The applicable event or vendor terms may apply in addition to these Terms.")),
             text("7. Payments",
                  p("Where payment is required, users must provide accurate payment information. Payment "
                    "processing may be handled by third-party payment providers.")),
             text("8. Memberships",
                  p("Buddilio may offer paid memberships or subscriptions. The applicable membership page will "
                    "specify price, duration, benefits, renewal terms and cancellation terms. Membership "
                    "benefits may change prospectively where permitted by applicable terms.")),
             text("9. Event passes and bookings",
                  p("Event passes and bookings may have individual cancellation policies. The cancellation "
                    "policy displayed before purchase will apply to the applicable booking, subject to "
                    "applicable law.")),
             text("10. Refunds",
                  p("Refund eligibility is governed by the applicable "
                    + link("Cancellation &amp; Refund Policy", "/p/refund")
                    + " and the specific product or event terms.")),
             text("11. User content",
                  p("You are responsible for content you upload. You must have the necessary rights to use "
                    "that content. Buddilio may remove content that violates applicable policies.")),
             text("12. Intellectual property",
                  p("Buddilio's branding, software, design, content and other intellectual property belong to "
                    "Buddilio or its licensors unless otherwise stated. You may not copy, reproduce, "
                    "distribute or commercially exploit Buddilio intellectual property without authorisation.")),
             text("13. Safety",
                  p("Users should review the " + link("Buddilio Safety Centre", "/safety")
                    + " before meeting another person. Buddilio does not guarantee personal safety or the "
                      "conduct of another user.")),
             text("14. Account suspension",
                  p("Buddilio may suspend or terminate accounts where reasonably necessary due to:") + ul([
                      "Policy violations", "Fraud", "Abuse", "Safety concerns", "Illegal activity", "Misuse",
                      "Repeated complaints", "Other serious violations"])),
             text("15. Disclaimer",
                  p("Buddilio provides a platform for discovery and interaction. Except where expressly "
                    "stated, Buddilio does not guarantee:") + ul([
                      "availability", "accuracy of every user-provided statement",
                      "suitability of a companion", "quality of third-party services",
                      "uninterrupted access", "specific social outcomes"])),
             text("16. Limitation of liability",
                  p("To the maximum extent permitted by law, Buddilio shall not be liable for indirect, "
                    "incidental, special or consequential losses arising from user interactions or "
                    "third-party services. Nothing in these Terms excludes liability that cannot legally be "
                    "excluded.")),
             text("17. Indemnification",
                  p("You agree to indemnify Buddilio against claims, losses or expenses arising from your "
                    "unlawful conduct, breach of these Terms or violation of another person's rights.")),
             text("18. Changes to Terms",
                  p("Buddilio may update these Terms from time to time. Continued use after an update may "
                    "constitute acceptance where permitted by law.")),
             text("19. Governing law",
                  p("These Terms shall be governed by the laws of India. Subject to applicable law, disputes "
                    f"shall be subject to the jurisdiction of the courts and tribunals having jurisdiction "
                    f"over {ENTITY['jurisdiction']}.")),
             text("Entity details",
                  p(f"{ENTITY['name']} · MSME registration {ENTITY['msme']} · {ENTITY['address']} · "
                    f"<a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>")),
             related_block("terms"))),

    # ---------------- Refund ----------------
    dict(slug="refund", title="Cancellation & Refund Policy",
         seo_title="Buddilio Cancellation & Refund Policy",
         seo_description="Understand Buddilio's cancellation and refund rules for memberships, event passes, "
                         "bookings and third-party services.",
         nav_footer_group="Legal", nav_label="Cancellation & Refund Policy", order=3,
         content=p("Buddilio wants customers to understand cancellation and refund conditions before making a "
                   "purchase. Refund eligibility depends on the type of purchase."),
         blocks=blocks(
             text("1. Memberships",
                  p("Membership purchases are subject to the membership terms displayed at the time of "
                    "purchase. Unless specifically stated otherwise, cancellation of a membership does not "
                    "automatically create a right to a refund for the unused portion of a membership period. "
                    "Where applicable law requires a refund, Buddilio will comply with that requirement.")),
             text("2. Event passes",
                  p("Event passes are governed by the cancellation policy displayed for the specific event. "
                    "Some event passes may be:") + ul(["Fully refundable", "Partially refundable",
                                                       "Refundable until a specified deadline",
                                                       "Non-refundable"])
                  + p("The applicable policy will be displayed before purchase where reasonably possible.")),
             text("3. Vendor services",
                  p("Where a service is provided by a third-party vendor, the vendor's applicable cancellation "
                    "policy may apply.")),
             text("4. Vendor cancellation",
                  p("If a vendor cancels a confirmed booking or cannot provide the purchased service, "
                    "Buddilio may provide an applicable refund or alternative remedy in accordance with the "
                    "applicable booking terms.")),
             text("5. No-show",
                  p("Unless the applicable event or service terms state otherwise, failure to attend a "
                    "confirmed booking may result in loss of the booking amount.")),
             text("6. Refund processing",
                  p("Approved refunds may be returned through the original payment method where reasonably "
                    "possible. Processing time may depend on the payment provider or financial institution.")),
             text("7. Chargebacks",
                  p("Customers should contact Buddilio Support before initiating a payment dispute where "
                    "appropriate. Fraudulent or abusive chargeback activity may result in account "
                    "restrictions.")),
             text("8. Duplicate transactions",
                  p("If you believe you have been charged twice for the same transaction, contact Buddilio "
                    "Support with the relevant transaction details.")),
             text("9. How to request a refund",
                  p(f"Contact <a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a> and include:")
                  + ul(["Name", "Registered email", "Booking or order ID", "Transaction reference",
                        "Reason for refund request"])),
             text("10. Important",
                  p("The refund policy displayed at the time of purchase may contain specific terms applicable "
                    "to that particular product, event or service. Where there is a conflict, the specific "
                    "purchase terms will govern to the extent permitted by law.")),
             related_block("refund"))),

    # ---------------- Cookies ----------------
    dict(slug="cookies", title="Cookie Policy",
         seo_title="Buddilio Cookie Policy",
         seo_description="How Buddilio uses cookies and similar technologies, and how you can control them.",
         nav_footer_group="Legal", nav_label="Cookie Policy", order=4,
         content=p("Buddilio uses cookies and similar technologies to operate and improve the platform. "
                   "Cookies may help us:")
                 + ul(["Keep users signed in", "Remember preferences", "Improve security",
                       "Understand website usage", "Improve performance", "Provide relevant functionality"]),
         blocks=blocks(
             text("Types of cookies",
                  h3("Essential cookies") + p("Required for core website functionality.")
                  + h3("Preference cookies") + p("Remember settings and preferences.")
                  + h3("Analytics cookies") + p("Help understand how visitors use the website.")
                  + h3("Security cookies") + p("Help detect suspicious activity and protect accounts.")),
             text("Managing cookies",
                  p("Most browsers allow users to control cookies through browser settings. Disabling certain "
                    "cookies may affect website functionality.")),
             related_block("cookies"))),

    # ---------------- Vendor terms ----------------
    dict(slug="vendor-terms", title="Buddilio Vendor Terms",
         seo_title="Buddilio Vendor Terms | Listing, Commercial & Pricing",
         seo_description="Vendors on Buddilio are governed by the Buddilio Vendor Listing, Commercial & "
                         "Pricing Agreement, accepted electronically in the vendor portal.",
         nav_footer_group="Legal", nav_label="Vendor Terms", order=5,
         content=p("Vendors listed on Buddilio are subject to the separate Buddilio Vendor Listing, Commercial "
                   "&amp; Pricing Agreement."),
         blocks=blocks(
             text("What the Vendor Agreement governs", ul([
                 "Vendor onboarding", "Listing authorisation", "Commission", "Vendor Net Rate",
                 "Pricing Floor", "Dynamic Pricing", "Promotions", "Payment collection", "Settlement",
                 "Cancellation", "Refunds", "Customer service", "Vendor compliance", "Non-circumvention",
                 "Suspension", "Termination"])),
             text("How it is accepted",
                  p("The complete Vendor Agreement is generated for each vendor from their approved profile "
                    "and Commercial Schedule, and is accepted electronically through the "
                    + link("Buddilio Vendor Portal", "/vendor/agreement")
                    + " with email OTP verification. Every acceptance is recorded and the executed PDF is "
                      "stored against the vendor account.")),
             related_block("vendor-terms"))),

    # ---------------- Contact ----------------
    dict(slug="contact", title="Contact Buddilio",
         seo_title="Contact Buddilio | Customer Support",
         seo_description="Contact Buddilio for account, membership, booking, payment, vendor, safety and "
                         "general support enquiries.",
         nav_footer_group="Buddilio", nav_label="Contact Us", order=4,
         content=p("Have a question, need assistance or want to report an issue? We're here to help."),
         blocks=blocks(
             text("General support",
                  p(f"Email: <a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>")
                  + p("For account, membership, booking, payment or general platform queries, please include "
                      "your registered email address and relevant booking or order reference where "
                      "applicable.")),
             text("Safety and community reports",
                  p("If you need to report harassment, fraud, abuse, threats, fake profiles, unsafe "
                    "behaviour, privacy concerns or community guideline violations, use the in-app reporting "
                    f"option or email <a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>. For urgent "
                    "physical safety situations, contact appropriate local emergency services first.")),
             text("Vendor support", p("Vendors may contact Buddilio regarding:") + ul([
                 "Account setup", "Listings", "Pricing", "Commission", "Bookings", "Settlements",
                 "Documents", "Agreement", "Technical issues"])),
             text("Business and partnerships",
                  p(f"For partnership and business enquiries: "
                    f"<a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>")),
             text("Registered details",
                  p(f"{ENTITY['name']} · {ENTITY['address']} · MSME {ENTITY['msme']}")),
             related_block("contact"))),

    # ---------------- Grievance ----------------
    dict(slug="grievance", title="Grievance & Support",
         seo_title="Buddilio Grievance & Support",
         seo_description="How to raise a grievance with Buddilio and what information to include.",
         nav_footer_group="", nav_label="Grievance", order=6,
         content=p("Buddilio is committed to addressing legitimate complaints and user concerns."),
         blocks=blocks(
             text("What to include",
                  p("When contacting us, please provide enough information for us to identify the relevant:")
                  + ul(["Account", "Booking", "Vendor", "Event", "Transaction", "Complaint"])
                  + p("We may request additional information where necessary. We aim to review complaints "
                      "within a reasonable period.")),
             text("Grievance Officer",
                  p(f"{ENTITY['grievance']} · {ENTITY['name']} · {ENTITY['address']} · "
                    f"<a href=\"mailto:{ENTITY['email']}\">{ENTITY['email']}</a>")),
             related_block("grievance"))),

    # ---------------- Cities ----------------
    dict(slug="cities", title="Cities We Serve",
         seo_title="Cities We Serve | Buddilio",
         seo_description="Buddilio is expanding social experiences, companions, events and lifestyle "
                         "activities across India. Availability varies by city.",
         nav_footer_group="Buddilio", nav_label="Cities We Serve", order=5,
         content=p("Buddilio is expanding its network of social experiences, companions, events and lifestyle "
                   "activities across India. Availability varies by city and category.",
                   "Users should check the platform for current listings and availability. Buddilio may add or "
                   "remove cities, services or experiences from time to time."),
         blocks=blocks(
             text("Browse by city",
                  p("Open " + link("Events", "/events") + " or " + link("Companions", "/companions")
                    + " and pick your city to see what's live right now.")),
             related_block("cities"))),

    # ---------------- Insights ----------------
    dict(slug="insights", title="Buddilio Insights",
         seo_title="Buddilio Insights | Social Experiences & City Guides",
         seo_description="Articles on social experiences, events, lifestyle, city guides, activities, travel, "
                         "dining, community and safety.",
         nav_footer_group="", nav_label="Insights", order=7,
         content=p("The Buddilio blog may include articles covering:")
                 + ul(["Social experiences", "Events", "Lifestyle", "City guides", "Activities", "Travel",
                       "Dining", "Community", "Safety", "Social confidence", "Experience discovery"])
                 + p("Content published on the Buddilio blog is intended for general informational purposes "
                     "and should not be treated as professional advice unless expressly stated."),
         blocks=blocks(related_block("insights"))),

    # ---------------- Trust ----------------
    dict(slug="trust", title="Safety & Trust",
         seo_title="Safety & Trust | Buddilio",
         seo_description="How Buddilio supports trust: responsible profiles, reporting, moderation, community "
                         "standards, secure payments, privacy protection and vendor verification.",
         nav_footer_group="Safety & Trust", nav_label="Safety & Trust", order=4,
         content=p("Buddilio believes that trust is essential to social discovery. We work to provide tools "
                   "and policies designed to support:")
                 + ul(["Responsible profiles", "Reporting", "Moderation", "Community standards",
                       "Secure payments", "Privacy protection", "Vendor verification where applicable",
                       "User education"])
                 + p("However, no platform can guarantee that every user or interaction will be safe. Users "
                     "should always exercise independent judgment."),
         blocks=blocks(
             text("Every Buddilio user is responsible for", ul([
                 "Providing truthful information", "Respecting other users",
                 "Protecting personal information", "Protecting financial information", "Following the law",
                 "Following Community Guidelines", "Following Safety Centre recommendations",
                 "Reporting suspicious behaviour", "Respecting consent and boundaries"])),
             related_block("trust"))),
]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    for page in PAGES:
        existing = await db.cms_pages.find_one({"slug": page["slug"]})
        body = {**page, "status": "published", "nav_header": False, "updated_at": now,
                "last_updated": now, "policy_version": (existing or {}).get("policy_version", 0) + 1,
                "updated_by_name": "Content seed"}
        if existing:
            await db.cms_page_versions.insert_one({
                "slug": page["slug"], "version": existing.get("policy_version", 1),
                "title": existing.get("title", ""), "content": existing.get("content", ""),
                "blocks": existing.get("blocks", []), "seo_title": existing.get("seo_title", ""),
                "seo_description": existing.get("seo_description", ""),
                "archived_at": now, "changed_by": existing.get("updated_by_name", "unknown")})
            await db.cms_pages.update_one({"_id": existing["_id"]}, {"$set": body})
            print(f"updated  /p/{page['slug']} → v{body['policy_version']}")
        else:
            await db.cms_pages.insert_one({**body, "created_at": now})
            print(f"created  /p/{page['slug']}")
    await db.settings.update_one({}, {"$set": {
        "footer_legal_note": FOOTER_NOTE,
        "vendor_entity": {"legal_name": ENTITY["name"], "entity_type": "Registered firm",
                          "signatory": "Manish Kumar", "signatory_title": "Authorised Signatory",
                          "email": ENTITY["email"], "msme": ENTITY["msme"], "gstin": "",
                          "address": ENTITY["address"], "jurisdiction": ENTITY["jurisdiction"]},
    }})
    print("settings updated")


if __name__ == "__main__":
    asyncio.run(main())
