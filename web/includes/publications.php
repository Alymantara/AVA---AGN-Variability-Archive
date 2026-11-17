<?php
/**
 * Key Project publications (newest first). Carried over from the legacy site.
 * Fields: title, authors, ref, year, ads (optional).
 */

declare(strict_types=1);

const AVA_ADS = 'https://ui.adsabs.harvard.edu/abs/';

const AVA_PUBLICATIONS = [
    ['The Extended Mrk 817 Reverberation Mapping Campaign. I. Swift Monitoring', 'Edelson et al.', 'ApJ, submitted', 2026, null],
    ['Broadband reverberation mapping of NGC 3783: a timescale-dependent optical lag spectrum', 'Vieliute et al.', 'MNRAS, submitted', 2026, null],
    ['Intensive NICER and Swift monitoring of NGC 4151 reveals disrupted X-ray reprocessing via a variable obscuring disk wind', 'Partington et al.', 'ApJ, submitted', 2026, null],
    ['Continuum Reverberation Mapping of the Super-Eddington Accreting AGN PG 0844+349', 'Huang et al.', 'MNRAS, submitted', 2026, null],
    ['Accretion Disk Reverberation Mapping of the Obscured Narrow-Line Seyfert 1 Galaxy Mrk 1239', 'Kololgi et al.', 'MNRAS, submitted', 2026, null],
    ['Directly Tracking the Rebrightening of a Supermassive Black Hole Accretion Disk', 'Middei et al.', 'ApJ, 1004, 200', 2026, '2026ApJ..1004..200M'],
    ['AGN STORM 2. XII. Ground-based Optical Photometry and Lag Measurements of Mrk 817', 'Montano et al.', 'ApJ, 1003, 147', 2026, '2026ApJ..1003..147M'],
    ['The unusually red delay spectrum of the low-mass black hole AGN NGC 4051 as revealed by intensive continuum reverberation mapping with the Las Cumbres Observatory', 'Marculewicz et al.', 'MNRAS, 548, 642', 2026, '2026MNRAS.548ag642M'],
    ['Intensive X-Ray/UVOIR continuum reverberation mapping of the Seyfert AGN MCG+08−11−11', 'Kynoch et al.', 'MNRAS, 546, 025', 2026, '2026MNRAS.546ag025K'],
    ['A Phenomenological Study of the Accretion Disk in the Super-Eddington AGN I Zw 1', 'Drewes et al.', 'MNRAS, 546, 67', 2026, '2026MNRAS.546ag067D'],
    ['Continuum reverberation mapping of accretion discs surrounding supermassive black hole binaries: observational signatures', 'Fu et al.', 'MNRAS, 543, 2093', 2025, '2025MNRAS.543.2093F'],
    ['Departures from standard disc predictions in intensive ground-based monitoring of three AGNs', 'Gonzalez-Buitrago et al.', 'MNRAS, 542, 2572', 2025, '2025MNRAS.542.2572G'],
    ['Echo mapping of the black hole accretion flow in NGC 7469', 'Prince et al.', 'MNRAS, 541, 642', 2025, '2025MNRAS.541..642P'],
    ['Testing X-ray Reprocessing and Mapping the Soft Excess of NGC 7469 with NICER', 'Partington et al.', 'ApJ, 986, 81', 2025, '2025ApJ...986...81P'],
    ['Accretion Disc Reverberation Mapping of the Quasar 3C 273', 'Thorne et al.', 'MNRAS, 537, 3746', 2025, '2025MNRAS.537.3746T'],
    ['Testing disc reprocessing models for AGN optical variability by comparison of X-ray and optical power spectra of NGC 4395', 'Beard et al.', 'MNRAS, 537, 293', 2025, '2025MNRAS.537..293B'],
    ['AGN STORM 2. VII. A Frequency-resolved Map of the Accretion Disk in Mrk 817: Simultaneous X-Ray Reverberation and UVOIR Disk Reprocessing Time Lags', 'Lewin et al.', 'ApJ, 974, 271', 2024, '2024ApJ...974..271L'],
    ['AGN STORM 2. VI. Mapping Temperature Fluctuations in the Accretion Disk of Mrk 817', 'Neustadt et al.', 'ApJ, 961, 219', 2024, '2024ApJ...961..219N'],
    ['Intensive Swift and LCO Monitoring of PG 1302–102: Active Galactic Nucleus Disk Reverberation Mapping of a Supermassive Black Hole Binary Candidate', 'Liu et al.', 'ApJ, 964, 167', 2024, '2024ApJ...964..167L'],
    ['The first spectroscopic IR reverberation programme on Mrk 509', 'Mitchell et al.', 'MNRAS, 529, 4824', 2024, '2024MNRAS.529.4824M'],
    ['X-ray/UVOIR Frequency-resolved Time Lag Analysis of Mrk 335 Reveals Accretion Disk Reprocessing', 'Lewin et al.', 'ApJ, 954, 33', 2023, '2023ApJ...954...33L'],
    ['Rimmed and rippled accretion disc models to explain AGN continuum lags', 'Starkey et al.', 'MNRAS, 519, 2754', 2023, '2023MNRAS.519.2754S'],
    ['Continuum Reverberation Mapping of Mrk 876 Over Three Years With Remote Robotic Observatories', 'Miller et al.', 'ApJ, 953, 137', 2023, '2023ApJ...953..137M'],
    ['UV/Optical disk reverberation lags despite a faint X-ray corona in the AGN Mrk 335', 'Kara et al.', 'ApJ, 947, 62', 2023, '2023ApJ...947...62K'],
    ['A complex dust morphology in the high-luminosity AGN Mrk 876', 'Landt et al.', 'ApJ, 945, 62', 2023, '2023ApJ...945...62L'],
    ['Testing Super-Eddington Accretion around a Supermassive Black Hole: Reverberation Mapping of PG 1119+120', 'Donnan et al.', 'MNRAS, 523, 545', 2023, '2023MNRAS.523..545D'],
    ['The luminosity-dependent contribution from the broad line region to the wavelength-dependent lags in Mrk 110', 'Vincentelli et al.', 'MNRAS, 512, L33', 2022, '2022MNRAS.512L..33V'],
    ['AGN STORM 2: I. First results: A Change in the Weather of Mrk 817', 'Kara et al.', 'ApJ, 922, 151', 2021, '2021ApJ...922..151K'],
    ['On the multi-wavelength variability of Mkn 110: Two components acting at different time-scales', 'Vincentelli et al.', 'MNRAS, 504, 4337', 2021, '2021MNRAS.504.4337V'],
    ['Intensive disc-reverberation mapping of Fairall 9: 1st year of Swift & LCO monitoring', 'Hernández Santisteban et al.', 'MNRAS, 498, 5399', 2020, '2020MNRAS.498.5399H'],
    ['Robotic reverberation mapping of the broad-line radio galaxy 3C 120', 'Hlabathe et al.', 'MNRAS, 497, 2910', 2020, '2020MNRAS.497.2910H'],
    ['Supermassive Black Holes with High Accretion Rates in Active Galactic Nuclei. XI. Accretion Disk Reverberation Mapping of Mrk 142', 'Cackett et al.', 'ApJ, 896, 1', 2020, '2020ApJ...896....1C'],
    ['The First Swift Intensive AGN Accretion Disk Reverberation Mapping Survey', 'Edelson et al.', 'ApJ, 870, 123', 2019, '2019ApJ...870..123E'],
    ['Stability of the Broad Line Region Geometry and Dynamics in Arp 151 Over Seven Years', 'Pancoast et al.', 'ApJ, 856, 108', 2018, '2018ApJ...856..108P'],
    ['Continuum Reverberation Mapping of the Accretion Disks in Two Seyfert 1 Galaxies', 'Fausnaugh et al.', 'ApJ, 854, 107', 2018, '2018ApJ...854..107F'],
    ['Reverberation Mapping of Optical Emission Lines in Five Active Galaxies', 'Fausnaugh et al.', 'ApJ, 840, 97', 2017, '2017ApJ...840...97F'],
    ['Space Telescope and Optical Reverberation Mapping Project. VI. Reverberating Disk Models for NGC 5548', 'Starkey et al.', 'ApJ, 835, 65', 2017, '2017ApJ...835...65S'],
    ['Space Telescope and Optical Reverberation Mapping Project. III. Optical Continuum Emission and Broadband Time Delays in NGC 5548', 'Fausnaugh et al.', 'ApJ, 821, 56', 2016, '2016ApJ...821...56F'],
    ['Robotic Reverberation Mapping of Arp 151', 'Valenti et al.', 'ApJL, 813, L36', 2015, '2015ApJ...813L..36V'],
];
