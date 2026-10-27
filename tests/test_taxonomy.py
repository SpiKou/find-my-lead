import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import taxonomy  # noqa: E402


def test_taxonomy_csvs_are_consistent():
    assert taxonomy.validate() == []


def test_name_rules():
    rule = taxonomy.match_name_rule
    assert rule("Τεχνικός Υπολογιστών Καλλιθέα") == ("it-services", "business")
    assert rule("Κεντρο Ξενων Γλωσσων Skills") == ("language-school", "business")
    assert rule("Ιωαννίδης Λογιστικό Γραφείο") == ("accountant", "business")
    assert rule("VCE - Βρανάκης Σύμβουλοι Μηχανικοί") == ("engineer-architect", "business")
    assert rule("Ταβέρνα Η Τράτα") == ("restaurant", "business")
    assert rule("Ποδοσφαιρικός Σύλλογος Αχαρνών") == (None, "organization")
    assert rule("2ο Δημοτικό Σχολείο Βύρωνα") == (None, "public")
    assert rule("ΙΕΚ Δέλτα") == ("private-school", "business")
    assert rule("Digital Marketing Lab") == ("marketing-agency", "business")
    assert rule("Mini Market Γιώργος") == ("grocery", "business")
    assert rule("Οικονομικές Υπηρεσίες Παπαδόπουλος") != ("lawyer", "business")
    assert rule("Ποτάμι") is None
    assert rule("Γλυκερία") is None
    assert rule("Χαρισιάδης Ανδρέου Συνεργείο Αυτοκινήτων") == ("car-repair", "business")
    assert rule("Service Υπολογιστών στην Παναγιούδα") == ("it-services", "business")
    assert rule("Klimahome Καραγιάννης") is None
    assert rule("GM Studio") is None
    assert rule("Εκκλησιαστικά Κληρόπουλος") != (None, "organization")
    assert rule("Κέντρα Σχολικής Μελέτης After School") == ("tutoring", "business")
    assert rule("Ναυτικός Όμιλος Σάμου") == (None, "organization")
    assert rule("Audiolize it Home Studio") is None
    assert rule("ΘΩΜΑΣ ηλεκτρολογικό υλικό") == ("hardware", "business")
