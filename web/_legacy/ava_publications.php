<?php
// Initialize the session
session_start();

?><!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AVA - AGN Variability Archive</title>
      <link rel="icon" 
      type="image/png" 
      href="favicon2.ico">
    <!-- Bootstrap -->
    <link href="//maxcdn.bootstrapcdn.com/bootstrap/3.2.0/css/bootstrap.min.css" rel="stylesheet">
    <link href="../assets/css/style_ava.css" rel="stylesheet">
    <link rel="stylesheet" href="http://aladin.u-strasbg.fr/AladinLite/api/v2/latest/aladin.min.css" />
	<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.13.0/css/all.css">
  	<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.13.0/css/v4-shims.css">

    <!-- you can skip the following line if your page already integrates the jQuery library -->
    <script type="text/javascript" src="http://code.jquery.com/jquery-1.9.1.min.js" charset="utf-8"></script> 
 
    <!-- to sort tables -->
    <!-- <script src="//ajax.googleapis.com/ajax/libs/jquery/1.11.0/jquery.min.js"></script>
    <script type="text/javascript" src="jquery-latest.js"></script> 
    <script type="text/javascript" src="jquery.tablesorter.js"></script> 
    -->
    
    <!--
    <script type="text/javascript" src="./jquery-latest.js"></script>
    <script type="text/javascript" src="./jquery.tablesorter.js"></script>
    -->
    <script type="text/javascript" src="sorttable.js"></script>

    <!-- HTML5 Shim and Respond.js IE8 support of HTML5 elements and media queries -->
    <!-- WARNING: Respond.js doesn't work if you view the page via file:// -->
    <!--[if lt IE 9]>
      <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
      <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
    <![endif]-->
    
    <script type='text/javascript'>
    //<![CDATA[
    var nW,nH,oH,oW;
    function zoomToggle(iWideSmall,iHighSmall,iWideLarge,iHighLarge,whichImage){
      oW=whichImage.style.width;oH=whichImage.style.height;
      if((oW==iWideLarge)||(oH==iHighLarge)){
        nW=iWideSmall;nH=iHighSmall;
      }else{
        nW=iWideLarge;nH=iHighLarge;
      }
      whichImage.style.width=nW;whichImage.style.height=nH;
    }
    //]]>
    </script>
</head>

<body>

<div class="container">
<h1><a href="http://www.alymantara.com/ava/index.php" style="color:black; text-decoration: none">AVA <small> AGN Variability Archive</small> <img src="../assets/images/banner.png" height="50"></a></h1>
  <div class="navbar navbar-default" role="navigation">
  
    <div class="navbar-header">
            <button type="button" class="navbar-toggle" data-toggle="collapse" data-target=".navbar-collapse">
              <span class="sr-only">Toggle navigation</span>
              <span class="icon-bar"></span>
              <span class="icon-bar"></span>
              <span class="icon-bar"></span>
            </button>
    </div>
    <div class="collapse navbar-collapse" id="">
    <ul class="nav navbar-nav">
      <li><a href="index.php" title="Homepage"><i class="fas fa-home"></i> AVA Archive</a></li>
      <li><a href="ava_about.php" title="About ">About</a></li>
      <li><a href="ava_data.php" title="Data Format ">Data Format</a></li>
      <li><a href="ava_live.php" title="Data Format ">Live Updates</a></li>
      <li><a href="ava_publications.php" title="Publications">Publications</a></li>
      <li><a href="ava_team.php" title="About ">Team</a></li>
                <li>
                <a href="swift_tracker.php" title="About">
                    Swift Orbit
                </a>
            </li>
      <!--<li><a href="index.php" title="References">References</a></li>-->
      <!--<li><a href="index.php" title="Citation, feedback and acknowledgements">Acknowledgement</a></li> -->
      <!--<li><a href="about.php" title="About this project">About</a></li>     </ul>-->
    </ul>
    <ul class="nav navbar-nav navbar-right">
  <?php
      if (isset($_SESSION['username'])) {
  // echo out a clickable image
  echo "<li><a class='btn btn-outline-primary' href='profile.php?id=". $_SESSION['username']."' role='button' style='color:black'> <i class='fas fa-user-alt'></i> <strong>". $_SESSION['username']."</strong> <i class='fas fa-sign-in'></i></a></li>";
  echo "<li><a class='btn btn-outline-primary' href='logout.php' role='button' style='color:red'> Logout <i class='fas fa-sign-in'></i></a></li>";
}
else {
  // echo non-clickable
  echo "<li><a class='btn btn-outline-primary' href='login.php' role='button' style='color:red'> <i class='fas fa-user-alt'></i> &nbsp Login <i class='fas fa-sign-in'></i></a></li>";
}
?>

    </ul>
    </div><!-- /.navbar-collapse -->
  </div><!--/.container-fluid -->
</div>

<div class="container"><!-- closes in header -->

  <h3>Acknowledgments<br/></h3>
  <p>If your work used the data please cite the corresponding paper for each target (as described in each target information). In addition, please acknowledge AVA as well, using the following citation:
  </p>

  <li> <strong>AVA - Active Galactic Nuclei Variability Archive</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Hernández Santisteban <a href="#" target="_blank">2026,  in prep. &nbsp</i></a></li>

  <h3>Publications<br/></h3>
  <p>
  The following publications concern the direct results of all three Key Projects dedicated to intensive broadband reverberation mapping of AGN:<br>

  <!--
  <li> <strong>      </strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp XXXXX et al., <a href="#" target="_blank">  in prep. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>


  <li> <strong>NGC 4151: TBD</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Myles et al., <a href="#" target="_blank">  in prep. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>


  <li> <strong>IBRM on NGC 3783</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Vieliute et al., <a href="#" target="_blank">  in prep. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>IBRM on Mrk 1044</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Johnston et al., <a href="#" target="_blank">  in prep. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>IBRM on NGC 6814</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Cornfield et al., <a href="#" target="_blank">  in prep. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>


  <li> <strong>Echo mapping of ESO 362-G18</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Gonzalez-Buitrago et al., <a href="#" target="_blank">  in prep. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>
  -->
<ol reversed>

  <li> <strong>Continuum Reverberation Mapping of the Super-Eddington Accreting AGN PG 0844+349</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Huang et al., <a href="#" target="_blank"> 2026, MNRAS, submitted. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Accretion Disk Reverberation Mapping of the Obscured Narrow-Line Seyfert 1 Galaxy Mrk 1239</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Kololgi et al., <a href="#" target="_blank"> 2026, MNRAS, submitted. &nbsp</i></a></li>

  <li> <strong>Directly Tracking the Rebrightening of a Supermassive Black Hole Accretion Disk</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Middei et al., <a href="https://ui.adsabs.harvard.edu/abs/2026ApJ..1004..200M/abstract" target="_blank"> 2026, ApJ, 1004, 200. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>AGN STORM 2. XII. Ground-based Optical Photometry and Lag Measurements of Mrk 817</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Montano et al., <a href="https://ui.adsabs.harvard.edu/abs/2026ApJ..1003..147M/abstract" target="_blank"> 2026, ApJ, 1003, 147. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>The unusually red delay spectrum of the low-mass black hole AGN NGC 4051 as revealed by intensive continuum reverberation mapping with the Las Cumbres Observatory</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Marculewicz et al., <a href="https://ui.adsabs.harvard.edu/abs/2026MNRAS.548ag642M" target="_blank"> 2026, MNRAS, 548, 642 &nbsp</a></li>

  <li> <strong>A Phenomenological Study of the Accretion Disk in the Super-Eddington AGN I Zw 1</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Drewes et al., <a href="https://ui.adsabs.harvard.edu/abs/2026MNRAS.546ag067D/abstract" target="_blank"> 2025, MNRAS, 546, 67. &nbsp</a></li>

  <li> <strong>Intensive X-Ray/UVOIR continuum reverberation mapping of the Seyfert AGN MCG+08−11−11</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Kynoch et al., <a href="https://ui.adsabs.harvard.edu/abs/2026MNRAS.546ag025K/abstract" target="_blank"> 2026, MNRAS, 546, 025. &nbsp</a></li> 

  <li> <strong>Continuum reverberation mapping of accretion discs surrounding supermassive black hole binaries: observational signatures</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Fu et al., <a href="https://ui.adsabs.harvard.edu/abs/2025MNRAS.543.2093F" target="_blank"> 2025, MNRAS, 543, 2093. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Departures from standard disc predictions in intensive ground-based monitoring of three AGNs</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Gonzalez-Buitrago et al., <a href="https://ui.adsabs.harvard.edu/abs/2025MNRAS.542.2572G" target="_blank"> 2025, MNRAS, 542, 2572. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Echo mapping of the black hole accretion flow in NGC 7469</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Prince et al., <a href="https://ui.adsabs.harvard.edu/abs/2025MNRAS.541..642P" target="_blank">  2025, MNRAS, 542, 642 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li> 
  
  <li> <strong>Testing X-ray Reprocessing and Mapping the Soft Excess of NGC 7469 with NICER</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Partington et al., <a href="https://ui.adsabs.harvard.edu/abs/2025ApJ...986...81P" target="_blank">  2025, ApJ, 986, 81 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>
  
  <li> <strong>Accretion Disc Reverberation Mapping of the Quasar 3C 273</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Thorne et al., <a href="https://ui.adsabs.harvard.edu/abs/2025MNRAS.537.3746T" target="_blank">  2025, MNRAS, 537, 3746 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li> 

  <li> <strong>Testing disc reprocessing models for AGN optical variability by comparison of X-ray and optical power spectra of NGC 4395</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Beard et al., <a href="https://ui.adsabs.harvard.edu/abs/2025MNRAS.537..293B" target="_blank"> 2025, MNRAS, 537, 293 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li> 

  <li> <strong>AGN STORM 2. VII. A Frequency-resolved Map of the Accretion Disk in Mrk 817: Simultaneous X-Ray Reverberation and UVOIR Disk Reprocessing Time Lags </strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Lewin et al., <a href="https://ui.adsabs.harvard.edu/abs/2024ApJ...974..271L/abstract" target="_blank"> 2024, ApJ, 974, 271 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li> 

  <li> <strong>AGN STORM 2. VI. Mapping Temperature Fluctuations in the Accretion Disk of Mrk 817 </strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Neustadt et al., <a href="https://ui.adsabs.harvard.edu/abs/2024ApJ...961..219N/abstract" target="_blank"> 2024, ApJ, 961, 219 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li> 

  <li> <strong>Intensive Swift and LCO Monitoring of PG 1302–102: Active Galactic Nucleus Disk Reverberation Mapping of a Supermassive Black Hole Binary Candidate</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Liu et al., <a href="https://ui.adsabs.harvard.edu/abs/2024ApJ...964..167L/abstract" target="_blank"> 2024, ApJ, 964, 167 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>The first spectroscopic IR reverberation programme on Mrk 509</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Mitchell et al., <a href="https://ui.adsabs.harvard.edu/abs/2024MNRAS.529.4824M/abstract" target="_blank"> 2024, MNRAS, 529, 4824 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>  

  <li> <strong>X-ray/UVOIR Frequency-resolved Time Lag Analysis of Mrk 335 Reveals Accretion Disk Reprocessing</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Lewin et al., <a href="https://ui.adsabs.harvard.edu/abs/2023ApJ...954...33L" target="_blank"> 2023, ApJ, 954, 33 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Rimmed and rippled accretion disc models to explain AGN continuum lags</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Starkey et al., <a href="https://ui.adsabs.harvard.edu/abs/2023MNRAS.519.2754S/abstract" target="_blank"> 2023, MNRAS, 519, 2754 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Continuum Reverberation Mapping of Mrk 876 Over Three Years With Remote Robotic Observatories</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Miller et al., <a href="https://ui.adsabs.harvard.edu/abs/2023ApJ...953..137M/abstract" target="_blank"> 2023, ApJ, 953, 137 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>UV/Optical disk reverberation lags despite a faint X-ray corona in the AGN Mrk 335 </strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Kara et al., <a href="https://ui.adsabs.harvard.edu/abs/2023ApJ...947...62K" target="_blank">  2023, ApJ, 947, 62  &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong> A complex dust morphology in the high-luminosity AGN Mrk 876</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Landt et al., <a href="https://ui.adsabs.harvard.edu/abs/2023ApJ...945...62L" target="_blank"> 2023, ApJ, 945, 62. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong> Testing Super-Eddington Accretion around a Supermassive Black Hole: Reverberation Mapping of PG 1119+120</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Donnan et al., <a href="https://ui.adsabs.harvard.edu/abs/2023MNRAS.523..545D" target="_blank"> 2023, MNRAS, 523, 545. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>The luminosity-dependent contribution from the broad line region to the wavelength-dependent lags in Mrk 110</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Vincentelli et al., <a href="https://ui.adsabs.harvard.edu/abs/2022MNRAS.512L..33V" target="_blank"> 2022, MNRAS, 512, 33. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>AGN STORM 2: I. First results: A Change in the Weather of Mrk 817 </strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Kara et al., <a href="https://ui.adsabs.harvard.edu/abs/2021ApJ...922..151K" target="_blank"> 2021, ApJ, 922, 151 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>On the multi-wavelength variability of Mkn 110: Two components acting at different time-scales</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Vincentelli et al., <a href="https://ui.adsabs.harvard.edu/abs/2021MNRAS.504.4337V/abstract" target="_blank"> 2021, MNRAS, 504, 4337 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Intensive disc-reverberation mapping of Fairall 9: 1st year of <i>Swift</i> & LCO monitoring</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Hernández Santisteban et al., <a href="https://ui.adsabs.harvard.edu/abs/2020MNRAS.498.5399H" target="_blank"> 2020, MNRAS, 498, 5399 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Robotic reverberation mapping of the broad-line radio galaxy 3C 120</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Hlabathe et al. <a href="https://ui.adsabs.harvard.edu/abs/2020MNRAS.497.2910H" target="_blank"> 2020, MNRAS, 497, 2910 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a></li>

  <li> <strong>Supermassive Black Holes with High Accretion Rates in Active Galactic Nuclei. XI. Accretion Disk Reverberation Mapping of Mrk 142</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp  Cackett et al. <a href="https://ui.adsabs.harvard.edu/abs/2020ApJ...896....1C/abstract" target="_blank"> 2020, ApJ, 896, 1 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>The First Swift Intensive AGN Accretion Disk Reverberation Mapping Survey</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Edelson,
  R. et al. <a href="https://ui.adsabs.harvard.edu/abs/2018ApJ...856..108P" target="_blank"> 2019, ApJ, 870, 123 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>Stability of the Broad Line Region Geometry and Dynamics in Arp 151 Over Seven Years</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Pancoast,
  A. et al. <a href="https://ui.adsabs.harvard.edu/abs/2018ApJ...856..108P" target="_blank"> 2018, ApJ, 856, 108 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>Continuum Reverberation Mapping of the Accretion Disks in Two Seyfert 1 Galaxies</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Fausnaugh, M.
  et al. <a href="https://ui.adsabs.harvard.edu/abs/2018ApJ...854..107F" target="_blank">2018, ApJ, 854, 107 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>Reverberation Mapping of Optical Emission Lines in Five Active Galaxies</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Fausnaugh, M. et al. <a href="https://ui.adsabs.harvard.edu/abs/2017ApJ...840...97F" target="_blank">2017, ApJ, 840, 97 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>Space Telescope and Optical Reverberation Mapping Project.VI. Reverberating Disk Models for NGC
  5548</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Starkey, D. et al.
   <a href="https://ui.adsabs.harvard.edu/abs/2017ApJ...835...65S" target="_blank">2017, ApJ, 835, 65 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>Space Telescope and Optical Reverberation Mapping Project. III. Optical Continuum Emission and Broadband Time Delays in NGC 5548</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Fausnaugh, M. et al. <a href="https://ui.adsabs.harvard.edu/abs/2016ApJ...821...56F" target="_blank">2016, ApJ, 821, 56 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>

  <li> <strong>Robotic Reverberation Mapping of Arp 151</strong>,<br>&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp Valenti, S. et al. <a href="https://ui.adsabs.harvard.edu/abs/2015ApJ...813L..36V" target="_blank">2015, ApJL, 813, 36 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a> </li>
</ol>
</p>

<div id="footer">
  <div class="col-md-7" align="left">
    <p class="muted credit"><small>&copy; 2020-2025 Juan V. Hernández Santisteban<br>
      Last Updated: <span id="demo"></span></small>
    <!--<br>
    <small>AVA acknowledges financial support to <a href='http://www.conicyt.cl/'   title='CONICYT' target="_blank">CONICYT</a> through the <a href='http://www.conicyt.cl/fondecyt/' title='FONDECYT' target="_blank">FONDECYT</a> project No. 3140310.</small>-->
    </p>
  </div> <!-- container -->
  <div class="col-md-1" align="right">
          <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons Licence" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png" /></a>
    </div>
    <div class="col-md-4" align="right">
    <p class="muted credit"><small>This work is licensed under a <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.</small></p>
    <!-- <a href="http://www.conicyt.cl/" target="_blank"><img alt="CONICYT" src="media/logo_conicyt.png" width="50" height="50" /></a> 
     <a href="http://www.conicyt.cl/fondecyt/" target="_blank"><img alt="FONDECYT" src="media/logo_fondecyt2.png" width="100" height="50" ></a>
     <a href="http://astro.uc.cl/" target="_blank"><img src="media/logo_puc2.png" width="50" height="50" alt="PUC" /></a>
     <a href="http://www.iac.es/index.php?lang=en" target="_blank"><img src="media/logo_iac.png" width="50" height="50" alt="IAC" /></a>-->
  </div>
  <!--<div id="logos" class="col-md-4" align="right">
     <a href="http://www.conicyt.cl/" target="_blank"><img alt="CONICYT" src="media/logo_conicyt.png" width="50" height="50" /></a> 
     <a href="http://www.conicyt.cl/fondecyt/" target="_blank"><img alt="FONDECYT" src="media/logo_fondecyt2.png" width="100" height="50" ></a>
     <a href="http://astro.uc.cl/" target="_blank"><img src="media/logo_puc2.png" width="50" height="50" alt="PUC" /></a>
     <a href="http://www.iac.es/index.php?lang=en" target="_blank"><img src="media/logo_iac.png" width="50" height="50" alt="IAC" /></a>
  </div>-->
</div> <!-- footer -->

  <!-- jQuery (necessary for Bootstrap's JavaScript plugins) -->
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.11.1/jquery.min.js"></script>
  <!-- Include all compiled plugins (below), or include individual files as needed -->
  <script src="//maxcdn.bootstrapcdn.com/bootstrap/3.2.0/js/bootstrap.min.js"></script>
    <script>
document.getElementById("demo").innerHTML = document.lastModified;
</script>
</body>
</html>