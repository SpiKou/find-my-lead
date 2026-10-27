# Φίλτρα και εξαγωγή

Τα φίλτρα ακολουθούν αυτά του leadcatalog.app. Κάθε φίλτρο αντιστοιχεί σε στήλη
του `businesses_<release>.parquet` (και αργότερα του πίνακα `businesses` στη βάση).

| Φίλτρο | Επιλογές | Στήλη | Κατάσταση |
|---|---|---|---|
| Αναζήτηση | Ελεύθερο κείμενο σε κλάδο, κατηγορία, περιφέρεια, πόλη, τεχνολογία | `industry_name`, `business_type_name`, `administrative_areas`, `localities`, `technologies` | Έτοιμο |
| Κλάδος | Οι κλάδοι του `industries.csv`, ο καθένας ανοίγει στις κατηγορίες του (`business_types.csv`). Όλα / Κανένα | `industry`, `business_type` | Έτοιμο |
| Τοποθεσία | Οι 13 περιφέρειες (+ Άγιον Όρος), με πόλεις ως υποεπιλογές | `administrative_areas`, `localities` | Έτοιμο |
| Website | Ενεργό, Ανενεργό, Χωρίς website | `website_status` (`active`, `inactive`, `none`) | `none` έτοιμο, `active`/`inactive` μετά το crawl (μέχρι τότε `unknown`) |
| Τεχνική κατάσταση | Τεχνικές αδυναμίες, Χαμηλό SEO score | `has_technical_weaknesses`, `has_low_seo` | Μετά το Lighthouse |
| Επικοινωνία | Email, Τηλέφωνο, Social profiles | `has_email`, `has_phone`, `has_social` | Έτοιμο |
| Τεχνολογία | WordPress, WooCommerce, Joomla, OpenCart, Wix, Shopify, Next.js, PrestaShop, Drupal, Magento, Angular, Squarespace, Webflow, Nuxt, React, Vue | `technologies` | Μετά το crawl |
| E-shop | Ναι | `eshop` | Μετά το crawl |

Τα φίλτρα μέσα στην ίδια ομάδα συνδυάζονται με OR (π.χ. Email ή Τηλέφωνο) και οι
ομάδες μεταξύ τους με AND.

Μέχρι να γίνει ο έλεγχος των websites, το Website έχει και την επιλογή «Μη
ελεγμένο» (`unknown`), και όσες επιλογές δεν έχουν ακόμα δεδομένα (Ενεργό,
Ανενεργό, Τεχνική κατάσταση, Τεχνολογία, E-shop) εμφανίζονται ανενεργές.

## Παράμετροι URL

Τα φίλτρα γράφονται στο URL, ώστε μια αναζήτηση να κοινοποιείται ή να μπαίνει
στους σελιδοδείκτες (`web/src/lib/filters.ts`):

| Παράμετρος | Τιμή | Παράδειγμα |
|---|---|---|
| `q` | Κείμενο στο όνομα (χωρίς τόνους, μέρος λέξης) | `q=φουρνος` |
| `industry` | Slug κλάδου ή `uncategorized` | `industry=food-retail` |
| `type` | Slug κατηγορίας | `type=accountant` |
| `region` | Περιφέρεια | `region=Περιφέρεια Αττικής` |
| `city` | `περιφέρεια\|πόλη` | `city=Περιφέρεια Αττικής\|Αθήνα` |
| `website` | `active`, `inactive`, `none`, `unknown` | `website=none` |
| `quality` | `weak`, `lowseo` | `quality=lowseo` |
| `contact` | `email`, `phone`, `social` | `contact=email` |
| `tech` | Όνομα τεχνολογίας | `tech=WordPress` |
| `eshop` | `1` | `eshop=1` |

Οι παράμετροι λίστας επαναλαμβάνονται (`contact=email&contact=phone`).

## Λίστα αποτελεσμάτων

Στήλες: Επιχείρηση (όνομα και ετικέτα κατάστασης website), Κατηγορία επιχείρησης
(κατηγορία και κλάδος), Περιοχή (πόλη, περιφέρεια), Επικοινωνία (ετικέτες Email,
Τηλέφωνο και ανά πλατφόρμα από το `social_platforms`). 20 αποτελέσματα ανά σελίδα
με «Φόρτωση περισσότερων», σύνολο αποτελεσμάτων, κοινοποίηση αναζήτησης (τα φίλτρα
στο URL) και εξαγωγή CSV.

## Εξαγωγή CSV

Οι 20 στήλες του LeadCatalog, από τα πεδία του `businesses`:

| Στήλη CSV | Πεδίο |
|---|---|
| business_name | `name` |
| business_type | `business_type_name` |
| industry | `industry_name` |
| website | `website` |
| website_status | `website_status` |
| emails | `emails` (με `; `) |
| phones | `phones` (με `; `) |
| social_urls | `socials` (με `; `) |
| locations | `locations` (με `; `) |
| locality | `localities` (με `; `) |
| administrative_area | `administrative_areas` (με `; `) |
| locations_count | `locations_count` |
| technologies | `technologies` (με `; `) |
| eshop | `eshop` |
| has_technical_weaknesses | `has_technical_weaknesses` |
| has_low_seo | `has_low_seo` |
| lighthouse_performance | `lighthouse_performance` |
| lighthouse_accessibility | `lighthouse_accessibility` |
| lighthouse_best_practices | `lighthouse_best_practices` |
| lighthouse_seo | `lighthouse_seo` |

## Τι δεν είναι lead

Οι τοποθεσίες με `entity_type` διαφορετικό από `business` (οργανώσεις, δημόσιο,
τόποι, υποδομές) δεν μπαίνουν στις επιχειρήσεις, αλλά μένουν στο
`locations_<release>.parquet` για μελλοντική χρήση.
