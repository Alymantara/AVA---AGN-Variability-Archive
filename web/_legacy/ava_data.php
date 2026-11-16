<?php
// Initialize the session
session_start();

?>
<!DOCTYPE html>
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
    <link
  rel="stylesheet"
  href="https://cdn.rawgit.com/afeld/bootstrap-toc/v1.0.1/dist/bootstrap-toc.min.css"
/>
	<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.13.0/css/all.css">
  	<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.13.0/css/v4-shims.css">
  <link rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.0.3/styles/default.min.css">

    <!-- you can skip the following line if your page already integrates the jQuery library -->
    <script type="text/javascript" src="http://code.jquery.com/jquery-1.9.1.min.js" charset="utf-8"></script> 
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.0.3/highlight.min.js"></script>
  <script>hljs.initHighlightingOnLoad();</script>
 
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

<!--<body data-spy="scroll" data-target="#toc">-->

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

<div class="container"><!-- closes in header -->
<div class="col-sm-2">
  <nav id="toc" data-toggle="toc" class="sticky-top"></nav>
</div>

<div class="col-sm-10">
  <p class="bg-info">
    <br>
 At the moment, the reduced data is <strong>only available for members of the 2023 LCO Key Project</strong>. If you are a member, please <a href="signup.php">sign-up</a> to AVA to request access to the data products.
<br>

</p>


<h3>Data reduction<br/></h3>
<p>The basic details of the data reduction are shown in Hernández Santisteban et al., <a href="https://ui.adsabs.harvard.edu/abs/2020MNRAS.498.5399H" target="_blank"> 2020, MNRAS, 498, 5399 &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a>. A more detailed explanation will be presented in the AVA paper (in prep.)</p>

<h3>Photometry<br/></h3>
<p>All the AVA products are delivered as CSV files. These can be found on the specific page for each AGN by clicking the <a><i class="fas fa-save"></i></a> symbol for each observatory. Below is the basic information to read the CSV files:</p>

<h5><u>Data format for Las Cumbres Observatory (LCO) data</u></h5>
  <p>
    Each file for a specific AGN and observatory are delivered as CSV files. These have 7 columns:
  <ol type="1">
    <li><strong>Object: </strong> Name of the AGN</li>
    <li><strong>Filter: </strong> Filter code (see table below)</li>
    <li><strong>MJD: </strong> Modified Julian Date, in days </li>
    <li><strong>Flux: </strong> in units of mJy</li>
    <li><strong>Error:</strong> in units of mJy </li>
    <li><strong>Telescope code: </strong> Unique code for each telescope in the LCO network. Used for intercalibration.</li>
    <li><strong>Site: </strong> Unique code for each observing site in the LCO network.</li>
  </ol>
  </p>

<h5><u>Data format for Swift/UVOT data</u></h5>
  <p>
    Each file for a specific AGN and observatory are delivered as CSV files. These have 7 columns:
  <ol type="1">
    <li><strong>-: </strong> Internal AVA ID number (ignore)</li>
    <li><strong>MJD: </strong> Modified Julian Date, in days </li>
    <li><strong>Filter: </strong> Filter code (see table below)</li>
    <li><strong>Flux: </strong> in units of erg s<sup>-1</sup> cm<sup>-1</sup> &#x212B;<sup>-1</sup></li>
    <li><strong>Error:</strong>in units of erg s<sup>-1</sup> cm<sup>-1</sup> &#x212B;<sup>-1</sup> </li>
    <li><strong>Flux: </strong> in units of mJy</li>
    <li><strong>Error:</strong> in units of mJy </li>
  </ol>
  </p>

<h5><u>Filters</u></h5>
  <p>For detailed information on the individual filters, central wavelengths we refer to the <a href="https://lco.global/observatory/instruments/filters/">LCO</a> and <a href="https://www.swift.ac.uk/analysis/uvot/filters.php">Swift/UVOT</a> websites:
  </p>

  <p>
    The following table contains the codes for each combination of observatory/filter used in the photometric data files:


  <div class="col-md-4" align="left">
  <table id="new" class="table table-hover table-striped width='50%' " bgcolor="#626F8F">
    <thead>
    <tr>
      <th class="th-lg" align="center" style="width: 16.66%" colspan="2">Swift</th>
    </tr>
      <tr>
      <th class="th-sm" align="center" style="width: 16.66%" >Filter Name</th>
      <th class="th-sm" align="center" style="width: 16.66%" >AVA Name</th>
    </tr>
    </thead>
      <tr>
      <td>UVW2</td>
      <td>W2</td>
      </tr>
        <tr>
      <td>UVM2</td>
      <td>M2</td>
      </tr>
          <tr>
      <td>UVW1</td>
      <td>W1</td>
      </tr>
        <tr>
      <td>U</td>
      <td>US</td>
      </tr>
          <tr>
      <td>B</td>
      <td>BS</td>
      </tr>
          <tr>
      <td>V</td>
      <td>VS</td>
      </tr>
      </table>
    </div> <!-- /.table-close -->

    <div class="col-md-4" align="middle">
  <table id="new" class="table table-hover table-striped width='50%' " bgcolor="#626F8F">
    <thead>
    <tr>
      <th class="th-lg" align="center" style="width: 16.66%" colspan="2">Las Cumbres Observatory</th>
    </tr>
      <tr>
      <th class="th-sm" align="center" style="width: 16.66%" >Filter Name</th>
      <th class="th-sm" align="center" style="width: 16.66%" >AVA Name</th>
    </tr>
    </thead>
      <tr>
      <td>Johnson U</td>
      <td>U</td>
      </tr>
        <tr>
      <td>Johnson B</td>
      <td>B</td>
      </tr>
          <tr>
      <td>Johnson V</td>
      <td>V</td>
      </tr>
        <tr>
      <td>SDSS <em>u</em></td>
      <td>u</td>
      </tr>
      <tr>
        <td>SDSS <em>g</em></td>
        <td>g</td>
      </tr>
      <tr>
        <td>SDSS <em>r</em></td>
        <td>r</td>
      </tr>
      <tr>
        <td>SDSS <em>i</em></td>
        <td>i</td>
      </tr>
      <tr>
        <td>Pan-STARRS <em>z<sub>s</sub></em></td>
        <td>z</td>
      </tr>
      </table>
    </div><!-- /.table-close -->

<div class="col-md-3" align="right">
  <table id="new" class="table table-hover table-striped width='50%' " bgcolor="#626F8F">
    <thead>
    <tr>
      <th class="th-lg" align="center" style="width: 16.66%" colspan="2">Liverpool Telescope</th>
    </tr>
      <tr>
      <th class="th-sm" align="center" style="width: 16.66%" >Filter Name</th>
      <th class="th-sm" align="center" style="width: 16.66%" >AVA Name</th>
    </tr>
    </thead>
        <tr>
      <td>SDSS <em>u</em></td>
      <td>uT</td>
      </tr>
      <tr>
        <td>SDSS <em>g</em></td>
        <td>gT</td>
      </tr>
      <tr>
        <td>SDSS <em>r</em></td>
        <td>rT</td>
      </tr>
      <tr>
        <td>SDSS <em>i</em></td>
        <td>iT</td>
      </tr>
      <tr>
        <td>SDSS <em>z<sub>s</sub></em></td>
        <td>zT</td>
      </tr>
      </table>
    </div><!-- /.table-close -->
    <br>
  </p>

 <div class="col-md-12" align="left">
  <h3>Intercalibration<br></h3>
  <p>
    The LCO data is obtained by a 12 1-m telescope network in six sites across the world. While these telescopes are identical by most accounts, they produce light curves which have small flux offsets of up to ~5% between all telescopes as shown in the image below. These systematic offsets are the result of small variations in the telescope/filter/CCD transmission which results in small amplitude shifts between the different telescopes at any given band. These offsets are often the dominant source of error in the photometric calibration accuracy, far larger than the photon noise. Thus, we strongly suggest AVA users to perform an intercalibration of all the data for each filter using <a href="https://github.com/FergusDonnan/PyROA">PyROA</a>.
  </p>
  <figure class="figure">
  <p style="text-align:center"><img src="../assets/images/f9_intercalib.png" class="img-responsive" alt="Responsive image">
  <figcaption class="figure-caption"><strong>Fig. 1 |</strong> The different telescopes in the LCO network (colors) have offsets from each other due to slight transmission differenes. The intercalibration procedure with <a href="https://github.com/FergusDonnan/PyROA">PyROA</a> produces a coherent light curve with ammended errorbars which reflect the scatter in the data.</figcaption></p>
</figure>


  <h3>Input for PyROA<br/></h3>
  <p>The following python code will allow you to separate the data file downloaded from AVA into the format required by <a href="https://github.com/FergusDonnan/PyROA"> PyROA</a> (Donnan et al., <a href="https://ui.adsabs.harvard.edu/abs/2023MNRAS.523..545D" target="_blank"> 2023, MNRAS, 523, 545. &nbsp<i class="fa fa-external-link" aria-hidden="true"></i></a>). The code will separate into individual files (AGNname_filter_telescope.dat) every filter and teelscope in the LCO network. This can then be easily used within PyROA to intercalibrate them into single merged files by filter. 
  <pre><code  class="python">def file_setup(file,output_dir='data',agn='AGN',verbose=False):
    '''AVA file setup for PyROA intercalibration.
       It will create a folder 
    INPUT:
        file: Lightcurve file as downloaded from AVA (string)
        output_dir: destination folder (string)
        agn: Name of the AGN used for the root files (string)
        verbose: Flag to output useful information about the dataset
                 (bool)
    '''
    from pandas import read_csv
    from os import mkdir
    from numpy import savetxt,array
    from pathlib import Path
    
    data = read_csv(file)
    unique_filters = data.Filter.unique()
    unique_telescopes = data.Tel.unique()
    
    my_file = Path(output_dir)
    if not my_file.is_dir():
        # directory exists
        os.mkdir(output_dir)
    else:
        # Warning
        print("WARNING: Overwriting files in "+output_dir)
    for i,fil in enumerate(unique_filters):
        for i,tel in enumerate(unique_telescopes):
            ss = (data.Filter == fil) & (data.Tel == tel)
            if ss.sum()> 0:
                savetxt(output_dir+'/'+agn+'_'+fil+'_'+tel+'.dat',array([data.MJD[ss].values,
                                                                 data.Flux[ss].values,
                                                                 data.Error[ss].values]).T)
                if verbose: print("Observations for {} - {}: {:7.0f}".format(fil,tel,ss.sum()))
            else:
                if verbose: print("No data for filter: {} and telescope: {}".format(fil,tel))</code></pre></p>
  <p>
  Simply add the function to your favourite script and run it to create the input files for PyROA.
  <pre><code  class="python"># It will save the new files in the default directory "data" (and create it)
    # if it doesn't exist
    file_setup('AVA_NGC_4051_lco.csv')

    # Change the root name to your files.
    file_setup('AVA_NGC_4051_lco.csv',output_dir='data_new',agn='NGC_4051')
  </code></pre></p>

  <h3>Eddington Ratio Calculations<br/></h3>
  <p> We have calculated the Eddington ratio by using the bolometric corrections, `k_{bol}` from Netzer 2022 where<br>
    <center>`k_{bol}= 40 \left(frac{L_{5100}}{10^42 }\right)^{-0.2}`</center><br>
     We caution that these Eddington ratios might be incorrect for very high-luminosity AGN.
  </p>

  <h3>Theoretical inter-band lags<br/></h3>
  <p> To help us designing our campaigns, we use the theoretical expectation of the lags for each AGN, given its average properties (black hole mass, Eddington ratio) following <a href="http://ui.adsabs.harvard.edu/abs/2016ApJ...821...56F/abstract" target="_blank"> Fausnaugh et al., (2016, ApJ, 821, 56)</a>:<br>
    <center>`\tau_{\lambda} - \tau_{\lambda_0}= frac{1}{c}\left(X frac{k\lambda}{hc}\right)^{4/3}\left[\left(frac{GM}{8\pi\sigma}\right)\left(frac{L_{Edd}}{\eta c^2}\right)(3+\kappa)\dot{m}_{Edd}\right]^{1/3}`</center><br>
     We caution that these Eddington ratios might be incorrect for very high-luminosity AGN.
  </p>
</div>
  </div>
  </div>
<div id="footer">
  <div class="col-md-7" align="left">
    <p class="muted credit"><small>&copy; 2020-2023 Juan V. Hernández Santisteban<br>
      Last Updated: <span id="demo"></span></small>
    <!--<br>
    <small>AVA acknowledges financial support to <a href='http://www.conicyt.cl/'   title='CONICYT' target="_blank">CONICYT</a> through the <a href='http://www.conicyt.cl/fondecyt/' title='FONDECYT' target="_blank">FONDECYT</a> project No. 3140310.</small>-->
    </p>
  </div> <!-- foot1 -->
    <div class="col-md-1" align="right">
          <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons Licence" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png" /></a>
    </div> <!-- foot2 -->
    <div class="col-md-4" align="right">
      <p class="muted credit"><small>This work is licensed under a <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.</small></p>
    <!-- <a href="http://www.conicyt.cl/" target="_blank"><img alt="CONICYT" src="media/logo_conicyt.png" width="50" height="50" /></a> 
     <a href="http://www.conicyt.cl/fondecyt/" target="_blank"><img alt="FONDECYT" src="media/logo_fondecyt2.png" width="100" height="50" ></a>
     <a href="http://astro.uc.cl/" target="_blank"><img src="media/logo_puc2.png" width="50" height="50" alt="PUC" /></a>
     <a href="http://www.iac.es/index.php?lang=en" target="_blank"><img src="media/logo_iac.png" width="50" height="50" alt="IAC" /></a>-->
    </div> <!-- foot3 -->
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
  <script src="https://cdn.rawgit.com/afeld/bootstrap-toc/v1.0.1/dist/bootstrap-toc.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.4/latest.js?config=AM_CHTML"></script>

    <script>
document.getElementById("demo").innerHTML = document.lastModified;
</script>
</body>
</html>