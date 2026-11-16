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
	  <link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.13.0/css/all.css">
  	<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.13.0/css/v4-shims.css">

    <!-- you can skip the following line if your page already integrates the jQuery library -->
    <script type="text/javascript" language="javascript" src="https://code.jquery.com/jquery-3.7.0.js"></script>
    <script type="text/javascript" language="javascript" src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>

    <!-- to sort tables -->
    <!-- <script src="//ajax.googleapis.com/ajax/libs/jquery/1.11.0/jquery.min.js"></script>
    <script type="text/javascript" src="jquery-latest.js"></script> 
    <script type="text/javascript" src="jquery.tablesorter.js"></script> 
    -->
    
    <!--
    <script type="text/javascript" src="./jquery-latest.js"></script>
    <script type="text/javascript" src="./jquery.tablesorter.js"></script>
    
    <script type="text/javascript" src="sorttable.js"></script>-->

    <!-- HTML5 Shim and Respond.js IE8 support of HTML5 elements and media queries -->
    <!-- WARNING: Respond.js doesn't work if you view the page via file:// -->
    <!--[if lt IE 9]>
      <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
      <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
    <![endif]-->
    
     <!--<script type='text/javascript'>
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
    </script>-->
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


<h3>Intensive broadband reverberation mapping targets<br/></h3>
<!--<div class="alert alert-warning" role="alert">
  17-Nov: There is an issue on our server which is preventing the update of all plots. 
</div>
-->

<?php

require_once('./includes/dbconnect.php');

$sql = "SELECT id,name,ra,decl,logl,Vmag,logm,redshift,lco_tot,swift_tot,ava_id,lco_B,lco_V,lco_u,lco_g,lco_r,lco_i,lco_z,swift_FX,lco_cadence,merged,swift_cadence,swift_jon,floyds_cadence FROM ava_test1  WHERE ava_id >= 0";
$result = $connection->query($sql);
?>


<h5>Select an object for more information</h5>
<p>
<small>
  <font color='#6ab04c'>Observing</font> = Data collected in the last 30 days.
  <font color='#0275d8'>Archived</font> = All the available data is processed and archived.  
  <!--<font color='#f0932b'>Programmed</font> = Observation campaigns are scheduled. -->
  <font color='#eb4d4b'>to be processed</font> = Target has been observed but <strong>not</strong> archived.
  <br>


</small>
  </p>
<!-- table-bordered table-responsive-sm 
style=";margin-left:auto;margin-right:auto;" -->
<div class="table-responsive" style=";margin-left:auto;margin-right:auto;">
<table id="ava_sample" class="table table-hover table-striped  w-auto width='100%' data-page-size='50' bgcolor='#626F8F'" >
<thead>
<tr>
    <th class="th-sm">ID <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">Name <br><span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">RA <br> (hms) <br><span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">DEC <br> (deg) <br><span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">g<sub>mag</sub><br>  <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">log(L<sub>Bol</sub>) <br> (erg/s) <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">log(M<sub>&#x25cf;</sub>) <br> (M<sub>&#8857;</sub>)<br> <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">redshift<br> <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">LCO<br>filters <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">Photo<br>&lt;&#916;t&gt;/d<br> <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">Spec<br>&lt;&#916;t&gt;/d<br> <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">Other<br>  <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <th class="th-sm">Status<br>  <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>
    <?php
      if (isset($_SESSION['username']) ) {
      echo  '<th class="th-lg" width="120pixels">Data<br><br> <span style="float:right;"><i class="fa fa-fw fa-sort"></i></span></th>';
      }
    ?>
</tr>
</thead><tbody>


<?php

if ($result->num_rows > 0) {
    // output data of each row
    while($row = $result->fetch_assoc()) {
      // Change colours for ongoing campaigns
      if ($row["ava_id"] == 2) {
          $color ="#6ab04c";
          $status = "Observing";
        }
      if ($row["ava_id"] == 0) {
          $color ="#eb4d4b";
          $status = "to be processed";
        } 
        if ($row["ava_id"] == 1) {
          $color ="#0275d8";
          $status ="Archived";
        }
        if ($row["ava_id"] == -1) {
          $color ="#f0932b";
          $status ="tba";
        }
    $filtros_lco ="";
      if ($row["lco_B"] >0) {$filtros_lco .="B";}
      if ($row["lco_V"] >0) {$filtros_lco .="V";}
      if ($row["lco_u"] >0) {$filtros_lco .="u";}
      if ($row["lco_g"] >0) {$filtros_lco .="g";}
      if ($row["lco_r"] >0) {$filtros_lco .="r";}
      if ($row["lco_i"] >0) {$filtros_lco .="i";}
      if ($row["lco_z"] >0) {$filtros_lco .="z";}
    $filtros_swi ="";
    if ($row["swift_FX"] >0) {$filtros_swi .="all";}
    //echo "	    <tbody>";
    echo "  <tr>";
    //echo "    <del>";
    echo "    <td><a href=info.php?id=". $row["id"].">". $row["id"]."</a></td>";
    echo "    <td><a href=info.php?id=". $row["id"].">". $row["name"]."</a></td>";
    //echo "    <td><a href=info.php?id=". $row["id"].">". $row["fname"]."</a></td>";
    echo "    <td>". $row["ra"]."</td>";
    echo "    <td>". $row["decl"]."</td>";
    echo "    <td>". number_format($row["Vmag"], 2, '.', '')."</td>";
    echo "    <td>". number_format($row["logl"], 2, '.', '')."</td>";
    //echo "    <td>". $row["logl"]."</td>";
    echo "    <td>". $row["logm"]."</td>";
    echo "    <td>". $row["redshift"]."</td>";
    echo "    <td>". $filtros_lco ."</td>";
    echo "    <td>". number_format($row["lco_cadence"], 2, '.', '')."</td>";
    echo "    <td>". number_format($row["floyds_cadence"], 1, '.', '')."</td>";
    echo "    <td>". $row["ava_id"]."</td>";
    echo "    <td><font color='". $color ."'>". $status ."</font></td>";
    if (isset($_SESSION['username']) ) {
      $data_icons = '';
      if ($row['lco_cadence'] > 0.0){$data_icons .= '<i class="fas fa-save" style="color:green" title="Extracted light curves" >&nbsp;';}
      if ($row['merged'] == 1){$data_icons .= '<i class="fas fa-save" style="color:orange" title="Merged light curves" >&nbsp;';}
      if (($row['swift_cadence'] > 0.0 && ($row["swift_jon"] == 2))){$data_icons .= '<i class="fas fa-save" title="Swift data available" style="color:purple">&nbsp;';}

      echo "    <td>". $data_icons."</td>";      
    }
    //echo "    </del>";
    echo "  </tr>";
    //echo "</tbody>";
    }
} else {
    echo "0 results";
}
$connection->close();
?>
   
</tbody>
<!--<caption>V<sub>mag</sub> is the average flux in the LCO band.log(L) and log(M) are obtained from our spectroscopic measurements or from Bentz catalogue. </caption>-->
</table>
</div>
   <script> 
  //     $(document).ready(function () {
  //     $('#ava_sample').DataTable({
  //     "ordering": true, // false to disable sorting (or any other option)
  //     "order": [[ 11, "desc" ],[ 2, "asc" ]],
  //     "pageLength": 50,
  //     scrollX: true,
  //     fixedColumns:   {
  //           left: 3,
  //       },

  //     //dom: "rtiplf",
  //     //dom: "fptlir",
  //     //responsive: true,
  //       "columnDefs": [
  // {
  //     "targets": [ 11 ],
  //     "visible": false,
  // }],
  //     });
  //     $('.dataTables_length').addClass('bs-select');
  //     });

  //     $(function () {
  //       $('[data-toggle="tooltip"]').tooltip()
  //     })

    $('#ava_sample').DataTable({
    "ordering": true, // false to disable sorting (or any other option)
    "order": [[ 11, "desc" ],[ 2, "asc" ]],
    "pageLength": 100,
    scrollX: true,
    "dom": '<"top"f>rt<"bottom"p><"clear">',
    "columnDefs": [
    {
        "targets": [ 11 ],
        "visible": false,
    }],
    });
  </script>
<p>
<small>Please <a href='ava_publications.html'>acknowledge</a> the use of this catalogue in any published work you derive from it. </small></p>
<hr>
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

</div>
  <!-- jQuery (necessary for Bootstrap's JavaScript plugins) -->
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.11.1/jquery.min.js"></script>
  <!-- Include all compiled plugins (below), or include individual files as needed -->
  <script src="//maxcdn.bootstrapcdn.com/bootstrap/3.2.0/js/bootstrap.min.js"></script>
<!--   <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.1.1/jquery.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/datatables/1.10.12/js/jquery.dataTables.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/datatables/1.10.13/js/dataTables.bootstrap4.min.js"></script> -->

  <script>
document.getElementById("demo").innerHTML = document.lastModified;
</script>




</body>
</html>