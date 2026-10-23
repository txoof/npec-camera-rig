raspberry.tips Case für Raspberry Pi 5 — Version 2.0
=====================================================

Ein parametrisches Gehäuse für den Raspberry Pi 5, gebaut um den offiziellen
Active Cooler und wahlweise einen M.2-HAT-Stapel.

Anleitung, Druckeinstellungen und die Konstruktionsentscheidungen dahinter:
https://raspberry.tips/3d-druck/raspberry-pi-5-gehaeuse-selbst-drucken


LIZENZ
------
Creative Commons Namensnennung 4.0 International (CC BY 4.0)
https://creativecommons.org/licenses/by/4.0/deed.de

Ihr dürft das Modell verändern, weitergeben und kommerziell nutzen.
Nennt dabei bitte die Quelle. Kopierfertige Zeile:

    Case für Raspberry Pi 5 von raspberry.tips, CC BY 4.0
    https://raspberry.tips/3d-druck/raspberry-pi-5-gehaeuse-selbst-drucken


INHALT
------
STL/        rpi5_case_B_wanne.stl          die Wanne
            rpi5_case_B_deckel.stl         der Deckel
            rpi5_case_B_kalibrierung.stl   Kalibrierstück, VOR dem Satz drucken
            rpi5_case_B_portlehre.stl      Lehre zum Prüfen der Portmaße

3MF/        rpi5_case_B_wanne.3mf          mit eingebettetem Druckprofil
            rpi5_case_B_deckel.3mf

OpenSCAD/   rpi5_case.scad                 die Quelle, parametrisch
            pi5_referenz.scad              Geistermodell des Pi 5 zur Sichtprüfung


DRUCKEINSTELLUNGEN
------------------
Schichthöhe    0,16 oder 0,2 mm an einer 0,4-mm-Düse
Perimeter      3 (der Deckelfalz ist nur 1,2 mm dick)
Infill         20 %, 4 Boden- und Deckelschichten
Stützen        nicht nötig
Brim           an, 5 mm
Material       PLA reicht; PETG bei Dauerlast oder Sonneneinstrahlung
Deckel         umgedreht drucken, Prägung auf dem Bett

Elefantenfuß-Kompensation einschalten (0,1 bis 0,2 mm). Das ist der häufigste
Grund dafür, dass der Deckel klemmt oder die Platine nicht zwischen die Dome passt.

Materialbedarf für Wanne + Deckel: rund 40 g.

Die mitgelieferten 3MF-Dateien sind mit 0,12 mm Schichthöhe gespeichert — mit diesem
Profil ist der saubere Deckel entstanden (48 Minuten). Für die Wanne und für schnellere
Drucke stellt ihr im Slicer auf 0,16 mm; darauf beziehen sich die Zeit- und
Gewichtsangaben im Artikel.


ERST KALIBRIEREN
----------------
Druckt zuerst rpi5_case_B_kalibrierung.stl (etwa 30 Minuten) und haltet es an
euren Pi. Vier Fragen, vier Parameter in rpi5_case.scad:

  Platine rutscht über die Zentrierzapfen, ohne zu klemmen?   zapfen_d
  USB- und HDMI-Stecker gehen ohne Zwang rein?                port_spiel
  Platine liegt auf den Domen, ohne unten anzustoßen?         unter_pcb
  Schrift lesbar, nicht zugelaufen?                           schrift_groesse


ANPASSEN
--------
rpi5_case.scad in OpenSCAD öffnen, Fenster > Customizer. Wichtige Parameter:

  part           wanne | deckel | kalibrierung | portlehre | vorschau
  variante       A = nur Active Cooler, B = mit M.2 HAT+
  hat_spacer     Spacer-Höhe eures HATs, die Gehäusehöhe rechnet sich neu
  port_spiel     Zugabe an den Buchsenöffnungen
  dom_typ        zapfen (schraubenlos) oder schraube
  fpc_schlitze   Schlitze für Kamera- und Display-Kabel
  wabe_schl      Größe der Lüftungswaben

Es gibt bewusst kein STEP: OpenSCAD kann kein STEP exportieren. Die .scad-Datei
ist die eigentliche Quelle und für Remixe deutlich brauchbarer.


HINWEISE
--------
Die Maße stammen aus dem offiziellen mechanischen Referenzmodell von
Raspberry Pi. Das Modell selbst gehört Raspberry Pi und ist hier bewusst NICHT
enthalten — verwendet wurden nur die daraus abgelesenen Maße.

Markenrecht: Nennt Ableitungen "Case für Raspberry Pi 5", nicht
"Raspberry Pi 5 Case", und verwendet kein Himbeer-Logo.

Haftung: Ein Gehäuse umschließt eine Wärmequelle. Die Kühlleistung ist nicht
vermessen. Keine Garantie für Dauerbetrieb, Nutzung auf eigene Gefahr.
