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
  <meta http-equiv="expires" content="0"> <!-- says that the cache expires 'now' -->
  <meta http-equiv="pragma" content="no-cache"> <!-- says not to use cached stuff, if there is any -->
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
         <script src="javascripts/d3.v3.min.js" charset="utf-8"></script>
        <script src="javascripts/c3.min.js"></script>

        <!-- Load papaparse.js -->
        <script src="javascripts/papaparse.min.js"></script>

    <script type="text/javascript" src="sorttable.js"></script>

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

<body onLoad="currentURL()">

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

<!--------------------------------->
<!-- * BH details -->
	<div class="row">
	<div class="col-md-6">

<?php
    //$id = mysql_real_escape_string( $_GET['EventID'] );
    $id = htmlspecialchars($_GET["id"]);
    //echo "test ". $id;

    require_once('./includes/dbconnect.php');

  $sql = "SELECT * FROM users WHERE username = '". htmlspecialchars($_SESSION['username'])."'";

  $result = $connection->query($sql);
  //$result2 = $connection2->query($sql2);

  if ($result->num_rows > 0) {
      // output data of each row
      while($row = $result->fetch_assoc()) {
      $usero = $row;

      // Check whether the user has access to that particular dataset.
      $length = 3;
      $string = substr(str_repeat(0, $length).$id , - $length);
      $name_var = 'AVA'.$string;

      if ($usero[$name_var] == 1){
          $access = 1;
         } else {
          $access = 0;
      }
$last_update = date("Y-m-d");
//$last_update = 'Hola';
#echo '<input type="hidden"  name="last_update" id="last_update" value="90234" readonly="readonly"/>';
//echo '        <input type="text" class="form-control" id="last_update" name="last_update" value="this is a new test" readonly>';

      } //close while
  } else {
      //echo "0 results";
  } //close while
  //$connection->close();
  //$connection2->close();


?>

<?php

	$sql = "SELECT * FROM ava_test1 WHERE id=". $id;

	$result = $connection->query($sql);

	if ($result->num_rows > 0) {
	    // output data of each row
	    while($row = $result->fetch_assoc()) {


    	//<!-- ####################################################### -->    
      echo '<div class="my-header">';
      echo '<h2><strong>'. $row["name"] .'</h2></strong>';
      //echo '<span><h4>AVA #'. $row["id"].$access .'<button class="btn btn-primary hBack" type="button"> <i class="fa fa-arrow-left" aria-hidden="true"></i>Back</button> </h4> </span> ';
      echo '<span><h4><button class="btn btn-primary hBack" type="button"> <i class="fa fa-arrow-left" aria-hidden="true"></i> Back</button> </h4> </span> ';
      //echo '';
      echo '</div>';
      echo '<div style="clear:both"></div>';
    	//echo '<h4>IDRM identification number #'. $row["id"] .'</h4>';
    	//echo '<h2><strong>'. $row["name"] .'</h2></strong>';
    	echo '<h4> <a target="_blank" href="http://simbad.u-strasbg.fr/simbad/sim-id?Ident='. $row["simbad_name"] .'"> Simbad </a>';
    	echo ' | <a target="_blank" href="https://ned.ipac.caltech.edu/byname?objname='. $row["simbad_name"] .'"> NED </a>';
    	if ($row["bentz_id"]>0){
    		echo ' | <a target="_blank" href="http://www.astro.gsu.edu/AGNmass/details.php?varname='. $row["bentz_id"] .'"> Bentz DB</a></h4>';
    	}
    	echo '<h4><strong>RA (h:m:s)&nbsp&nbsp;&nbsp;&nbsp;DEC (d:m:s)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;RA (deg) &nbsp;&nbsp;&nbsp; DEC (deg)</strong>:<br>';
    	echo "   ". $row["ra"] ."&nbsp;&nbsp;&nbsp;". $row["decl"] ."   &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;". $row["ra_deg"] ."&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;". $row["dec_deg"] ."<br>";
    	echo '</h4>';
        //   ( <a href='http://adsabs.harvard.edu/abs/2017ATel10711....1R' title='ADS' target='_blank'>Russell2017</a>  )</h4>
    	//echo "<h4><strong># of outbursts after discovery:</strong> <h4></strong>";
    	//echo "<h4><strong><font color='red'></font></strong></h4>";
    	//echo "<h4><font color='red'></font></h4>";
    	//echo "<h4><strong><font color='red'></font></strong></h4>";
        //echo "<br>";
        echo '    <table class="table table-hover text-nowrap">      ';
        echo '<caption><h4><strong>Basic Information</strong></h4></caption>';
        
        //echo "<!-- DISTANCE -->";
        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>Redshift</th>";
        echo "    <td class='th-sm' style='text-align:right'>". $row["redshift"] ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <td class='th-lg' style='text-align:right'><a target='_blank' href='https://ui.adsabs.harvard.edu/abs/". $row["red_url"] ."/abstract'> ". $row["red_cite"] ."</a></td>";        
        echo "</tr>";

        // ------ E(B-V) -------
        echo "<tr data-toggle='collapse' data-target='#demo1' class='accordion-toggle'> ";
        echo "    <td class='th-sm' style='width:  8.33%'> <button class='btn btn-default btn-xs'><span class='glyphicon glyphicon-eye-open'></td>";
        echo "    <th class='th-lg'>E(B-V)</th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["ebv"], 3, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'></td>";
        echo "    <td class='th-sm' style='text-align:right' ><a target='_blank' href='https://ui.adsabs.harvard.edu/abs/2011ApJ...737..103S/abstract'> Schlafly & Finkbeiner (2011)</a></td>";
        echo "</tr>";

        echo "<tr>";
        echo "    <td colspan='10' class='hiddenRow'>";
        echo "    <div id='demo1' class='accordian-body collapse'>";
        echo "    <table class='table table-hover text-nowrap'>";      

        echo "    <tr data-toggle='collapse'  class='accordion-toggle' data-target='#demo10'>";

        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>E(B-V)</th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["ebv_sfd"], 3, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'></td>";
        echo "    <td class='th-sm' style='text-align:right' ><a target='_blank' href='http://adsabs.harvard.edu/abs/1998ApJ...500..525S'> Schlegel et al., (1998)</a></td>";
        echo "</tr>";

        echo "    <tr>";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>N<sub>H</sub></th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["nh"], 3, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'>x10<sup>20</sup> cm<sup>-2</sup></td>";
        echo "    <td class='th-sm' style='text-align:right' ><a target='_blank' href='https://ui.adsabs.harvard.edu/abs/2016A%26A...594A.116H/abstract'> HI4PI Collaboration et al. (2016)</a></td>";
        echo "</tr>";

        echo "    <tr>";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>E(B-V)</sub></th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["ebv_w11"], 3, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'></td>";
        echo "    <td class='th-sm' style='text-align:right' ><a target='_blank' href='https://ui.adsabs.harvard.edu/#abs/2011A%26A...533A..16W'> Watson (2011)</a></td>";
        echo "</tr>";

        echo "</table";
        echo "    </div></td>";
        echo "</tr>";

        // ------ Black Hole mass -------
        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>Black Hole Mass</th>";
        echo "    <td class='th-sm' style='text-align:right'>". $row["logm"] ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'>M<sub>&#8857;</sub></td>";
        echo "    <td class='th-lg' style='text-align:right'><a target='_blank' href='https://ui.adsabs.harvard.edu/abs/". $row["logm_url"] ."/abstract'> ". $row["logm_cite"] ."</a></td>";
        echo "</tr>";
        
        //----- L_5100 ------
        if ($row["l_5100"] >0){
        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>log(L<sub>5100</sub>)</th>";
        echo "    <td class='th-sm' style='text-align:right'>". $row["l_5100"] ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'> erg/s </td>";
        echo "    <td class='th-lg' style='text-align:right'><a target='_blank' href='https://ui.adsabs.harvard.edu/abs/". $row["l_5100_url"] ."/abstract'> ". $row["l_5100_cite"] ."</a></td>";        
        echo "</tr>";}


        //----- L_bol ------
        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>log(L<sub>Bol</sub>)</th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["logl"], 2, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'>erg/s</td>";
        if ($row["l_5100"] >0){
        echo "    <td class='th-lg' style='text-align:right'>". $row["logl_comment"] .", <a href='https://ui.adsabs.harvard.edu/abs/2019MNRAS.488.5185N/abstract'>Netzer (2019)</a></td>";}
        if ($row["l_5100"] <0){
        echo "    <td class='th-lg' style='text-align:right'><a target='_blank' href='https://ui.adsabs.harvard.edu/abs/". $row["logl_url"] ."/abstract'> ". $row["logl_cite"] ."</a></td>";        
        echo "</tr>";}
        
        echo "</tr>";
        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";

        echo "    <th class='th-lg'>L<sub>Edd</sub></th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["ledd"], 3, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'></td>";
        echo "    <td class='th-lg' style='text-align:right'>(caution)</td>";
        echo "</tr>";

        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>Lag <em>u-g</em></th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["lag_uz"], 2, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'>days</td>";
        echo "    <td class='th-lg' style='text-align:right'>(theoretical)</td>";
        echo "</tr>";

        echo "<tr> ";
        echo "    <td class='th-sm' style='width:  8.33%'> </td>";
        echo "    <th class='th-lg'>Lag <em>u-z<sub>s</sub></em></th>";
        echo "    <td class='th-sm' style='text-align:right'>". number_format($row["lag_gz"], 2, '.', '') ."</td>";
        echo "    <td class='th-sm' style='width:  8.33%'>days</td>";
        echo "    <td class='th-lg' style='text-align:right'>(theoretical)</td>";
        echo "</tr>";

        if (isset($_SESSION['username'])) {
          echo "<tr> ";
          echo "    <td class='th-sm' style='width:  8.33%'> </td>";
          echo "    <th class='th-lg'>Comments:</sub></th>";
          echo "    <td class='th-lg' colspan='3'>". $row["comment"] ."</td>";
          //echo "    <td class='column-val' ></td>";
          //echo "    <td class='column-val' ></td>";
          echo "</tr>";
          echo "<tr> ";
          echo "    <th class='th-lg'>PI:</sub></th>";
          echo "    <td class='th-lg' colspan='3'>". $row["PI"] ."</td>";
          //echo "    <td class='column-val' ></td>";
          //echo "    <td class='column-val' ></td>";
          echo "</tr>";
        }

        //echo "<!-- Z -->";
        //echo "<tr>     ";
        //echo "    <th>d above plane (z)</th>";
        //echo "    <td>". $row["id"] ."</td>";
        //echo "    <td>(kpc)</td>";
        //echo "    <td> <a href='http' title='ADS' target='_blank'></a> </td>";
    	//echo "</tr>";
    	//echo "    <!-- NOTES -->";
    	//echo "<tr>     ";
    	//echo "    <th>Notes</th>";
    	//echo "    <td colspan="3"></td>";
    	//echo "</tr>";
    	//echo "</table>";
    	//// Finishes first table
    	//echo '<table class="table table-hover" style="width:100%">    ';
		echo '</table>';
        #echo '  </div>';
    echo $row["swift_XF"];
    // PHOTOMETRIC TABLE SUMMARY
	echo '<table class="table table-hover w-auto" style="width:130%"  >    ';
    echo '<caption><h4><strong>Photometric Data Summary</strong></h4></caption>';
    echo '<tr>';
    echo '    <th class="th-lg">Facility</th>';
    echo '    <td class="column-val" align="center">Cadence<br>(days)</td>';
    echo '    <td class="th-lg" align="center" >Start<br>(MJD)</td>';
    echo '    <td class="th-lg" align="center" >End<br>(MJD)</td>';
    echo '    <td class="th-lg" align="center"style="width:  8.33%"><i class="fas fa-download"></i></td>';    
    echo '</tr>';
    if ($row["swift_cadence"] >0){
    echo '<tr>';
    echo '    <th class="th-lg">Swift</th>';
    echo '    <td class="column-val" align="center">'. number_format($row["swift_cadence"], 2, '.', '') .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["swift_start"] .'</td>';  
    echo '    <td class="th-lg" align="center">'. $row["swift_end"] .'</td>';  
    if (isset($_SESSION['username']) && ($access == 1) && ($row["swift_jon"] == 2)) {
      // echo out a clickable image
    //echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="../assets/ava_photo/'. $row["data_id"] .'_photo.csv" download><i class="fas fa-save"></i></a></td>';
    echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="simpleDown_swift.php?id='. $row["data_id"] .'" download><i class="fas fa-save" style="color:Purple"></i></a></td>';
    }
    else {
      // echo non-clickable
    echo '    <td class="th-lg" align="center" style="width:  8.33%"><i class="fas fa-ban" style="color:black"></td>';
    }
    echo '</tr>';}
    if ($row["lco_cadence"] >0){
    echo '<tr>';
    echo '    <th class="th-lg">LCO</th>';
    echo '    <td class="column-val" align="center">'. number_format($row["lco_cadence"], 2, '.', '') .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["lco_start"] .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["lco_end"] .'</td>';
    if ($row["public"] == 1) {
      // echo out a clickable image
    //echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="../assets/ava_photo/'. $row["data_id"] .'_photo.csv" download><i class="fas fa-save"></i></a></td>';
    echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="simpleDown.php?id='. $row["data_id"] .'" download><i class="fas fa-save"></i></a></td>';
    }
    else {
      // echo non-clickable
      //https://archive.lco.global/?target_name=Mrk%20817&start=2022-02-01%2000%3A00&end=2022-07-31%2023%3A59&public=true&limit=20
    echo '    <td class="th-lg" align="center" style="width:  8.33%"><i class="fas fa-ban" style="color:black"></td>';
    }

    echo '</tr>';}
      if (isset($_SESSION['username'])) {
      echo '<tr>';
      echo '    <th class="th-lg"></th>';
      echo '    <td class="column-val" align="center"></td>';
      echo '    <td class="th-lg" align="center"><img src="LCO_logo.png" height="15" alt="alternatetext"></td>';
      echo '    <td class="th-lg" align="center"><span style="color:blue">Raw Images</span></td>';
      $lco_data = 'https://archive.lco.global/?target_name='.$row["lco_id"].'&start='.$row["lco_start"].'%2000%3A00&end='.$row["lco_end"].'%2023%3A59&public=true&limit=50';
      echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="'. $lco_data .'" target=”_blank”><i class="fa fa-external-link" style="color:blue"></i></a>';
      echo '</tr>';
      }

    if (isset($_SESSION['username']) && ($access == 1)) {
      echo '<tr>';
      echo '    <th class="th-lg"></th>';
      echo '    <td class="column-val" align="center"></td>';
      echo '    <td class="th-lg" align="center"></td>';
      echo '    <td class="th-lg" align="center"><span style="color:green">Extracted LCs</span></td>';
      echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="simpleDown.php?id='. $row["data_id"] .'" download><i class="fas fa-save" style="color:green"></i></a>';
      echo '</tr>';
      }
    if (isset($_SESSION['username']) && ($access == 1) && ($row["merged"] ==1)) {
      echo '<tr>';
      echo '    <th class="th-lg"></th>';
      echo '    <td class="column-val" align="center"></td>';
      echo '    <td class="th-lg" align="center"></td>';
      echo '    <td class="th-lg" align="center"><span style="color:orange">Merged LCs</span></td>';
      echo '    <td class="th-lg" align="center" style="width:  8.33%"><a href="simpleDown_merged.php?id='. $row["data_id"] .'" download><i class="fas fa-save" style="color:orange"></i></a>';
      echo '</tr>';
    }
    if ($row["lt_cadence"] >0){
    echo '<tr>';
    echo '    <th class="th-lg">LT</th>';
    echo '    <td class="column-val" align="center">'. number_format($row["lt_cadence"], 2, '.', '') .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["lt_start"] .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["lt_end"] .'</td>';
    echo '    <td class="th-lg" align="center" style="width:  8.33%">--</td>';
    echo '</tr>';}
    if ($row["hst_0"] >0){
    echo '<tr>';
    echo '    <th class="th-lg" align="center">HST</th>';
    echo '    <td class="column-val align="center"">'. $row["hst_tot"] .'</td>';
    echo '    <td class="th-lg" align="center">--</td>';
    echo '    <td class="th-lg" align="center">--</td>';
    echo '    <td class="th-lg" align="center" style="width:  8.33%">--</td>';
    echo '</tr>';}
    echo '</table>';

    // SPECTROSCOPIC TABLE SUMMARY
    if ($row["floyds_epochs"] >0){
    echo '	    <table class="table table-hover w-auto" style="width:130%">    ';
    echo '<caption><h4><strong>Spectroscopic Data Summary</strong></h4></caption>';
    echo '<tr>';
    echo '    <th class="column-name-list">Facility</th>';
    echo '    <td class="column-val" align="center" >Cadence<br>(days)</td>';
    echo '    <td class="column-val"align="center" >Epochs</td>';
    echo '    <td class="th-lg" align="center" >Start<br>(MJD)</td>';
    echo '    <td class="th-lg"align="center" >End<br>(MJD)</td>';
    echo '    <td class="column-val" align="center" ><i class="fas fa-download"></i></td>';    
    
    echo '<tr>';
    echo '    <th class="th-lg">LCO</th>';
    echo '    <td class="column-val" align="center">'. number_format($row["floyds_cadence"], 2, '.', '') .'</td>';
    echo '    <td class="column-val" align="center">'. number_format($row["floyds_epochs"], 0, '.', '') .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["floyds_start"] .'</td>';
    echo '    <td class="th-lg" align="center">'. $row["floyds_end"] .'</td>';
    echo '    <td class="th-lg" align="center" style="width:  8.33%"><i class="fas fa-ban" style="color:black"></td>';
    echo '</tr>';
    echo ' </table>';}

    echo ' <h3> Data Citation </h3>';
    echo '<p>';
    //echo '<li><a target="_blank" href="https://ui.adsabs.harvard.edu/abs/'. $row["cite_url"] .'"> '. $row["cite_name"] .'</a></li><br>';
    $citas_url = explode("|", $row["cite_url"]);
    $citas_nam = explode("|", $row["cite_name"]);
    //echo $citas_url,$citas_nam;
    #echo var_dump(count($citas_nam));
    for ($x = 0; $x < count($citas_nam)-1; $x++) {
        echo '<li><a target="_blank" href="https://ui.adsabs.harvard.edu/abs/'. $citas_url[$x] .'"> '. $citas_nam[$x] .'</a></li>';}
    echo '<br><small> Please use this reference if you use the this object data.</small>';
    echo '<br></p>';
    //echo ' JVHS';

    
    
    

	echo '	</div>';


    //<!-- ####################################################### -->    

    //echo '<!-- Aladin finding chart -->';
    //echo '<div id ="chart" class="col-md-4" style="margin:5px 50px 50px 300px;" align="center">';
    //echo '    Scroll to zoom. Set survey image in Controls        <h5>Default image: DSS2 Red</h5>';
    //echo '    <div id="aladin-lite-div" style="width:400px;height:400px;"></div>';
    //echo '    <a href="http://simbad.u-strasbg.fr/simbad/sim-id?Ident='. $row["name"] .'//+&NbIdent=1&Radius=2&Radius.unit=arcmin&submit=submit+id" title="Object information in Aladin" //target="_blank">'. $row["name"] .' in Simbad</a>    </div>';
    //echo '<script type="text/javascript" src="http://aladin.u-strasbg.fr/AladinLite/api/v1/aladin.min.js" //charset="utf-8"></script>';
    //echo '<script type="text/javascript">';
    //echo '  var aladin = $.aladin("#aladin-lite-div", {survey: "P/DSS2/red", zoom:0.1, 
    //    target: "17 58 40.04-33 48 26.80", cooFrame: "J2000"}); ';
    //echo '</script>';
    
    
    //<!-- Finding chart -->
    echo ' <div id ="chart" class="col-md-5" style="margin:0px 0px 0px 50px;" align="center" >';
    echo '   <h4 align="center">Photometric Light curves</h4><br><p>';
    //echo '     <font size=2>';
    //echo '     Click to enlarge in new tab/window<br>';
    //echo '     <span style="color:#F00;">Object marked with lines         </font>';
    //echo '     <br>';
    //echo '     <hr>';
    //echo '     <p align="left"></p>';
    //echo '     <a href="fchart.php?id=4" target="_blank" >';
    //echo '       <img src="../assets/ava_stills/'. $row["data_id"] .'_lcs.png" style="width:400px;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    
    echo '<ul class="nav nav-tabs">';
    echo '  <li class="active"><a data-toggle="tab" href="#photo">Photometry</a></li>';
    echo '  <li><a data-toggle="tab" href="#image">Image</a></li>';
    echo '  <li><a data-toggle="tab" href="#sky">Sky</a></li>';
    echo '  <li><a data-toggle="tab" href="#stan">Standards</a></li>';
    if ($row["floyds_rdy"] >0){
      echo '  <li><a data-toggle="tab" href="#spec">Spectroscopy</a></li>';}
    echo '</ul>';

    echo '<div class="tab-content">';
    echo '  <div id="photo" class="tab-pane fade in active">';
    echo '  <div class="tabbable">';
    echo '      <ul class="nav nav-tabs">';
    echo '          <li class="active"><a data-toggle="tab" href="#photo_orig">LCO</a></li>';
    echo '          <li><a data-toggle="tab" href="#photo_last6">LCO last 60 d</a></li>';
    if ($row["merged"] ==1 ){
    echo '          <li ><a data-toggle="tab" href="#photo_merged">LCO merged</a></li>';}
    if ($row["swift_cadence"] >0 && $row["swift_jon"] ==2){
        echo '      <li><a data-toggle="tab" href="#photo_swift">Swift</a></li>';}
    echo '      </ul>';
    echo '      <div class="tab-content">';
    echo '          <div id="photo_merged" class="tab-pane fade">';
    echo '              <p> <img src="plots/lco_latest_'. $row["data_id"] .'_merged_pytics.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    //echo '              <p> <img src="http://www-star.st-and.ac.uk/~jvhs1/ava_plots/lco_latest_'. $row["data_id"] .'_merged.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '          </div>';

    echo '          <div id="photo_last6" class="tab-pane fade">';
    if ($row["lco_cadence"] >0){
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_last6.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';}
    //echo '          <p> <img src="http://www-star.st-and.ac.uk/~jvhs1/ava_plots/lco_latest_'. $row["data_id"] .'_last6.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';}
    else {echo '          <br><p> Data not processed</p>';}
    echo '           </div>';
    if ($row["swift_cadence"] >0 && $row["swift_jon"]==1){
    echo '          <div id="photo_swift" class="tab-pane fade">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_swift.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    //echo '          <p> <img src="http://www-star.st-and.ac.uk/~jvhs1/ava_plots/lco_latest_'. $row["data_id"] .'_swift.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    if ($row["swift_cadence"] >0 && $row["swift_jon"]==2){
    echo '          <div id="photo_swift" class="tab-pane fade">';
    echo '          <p> <img src="plots/swift_latest_'. $row["data_id"] .'.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    //echo '          <p> <img src="http://www-star.st-and.ac.uk/~jvhs1/ava_plots/swift_latest_'. $row["data_id"] .'.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    echo '          <div id="photo_orig" class="tab-pane fade in active">';
    if ($row["lco_cadence"] >0){
    echo '              <p> <img src="plots/lco_latest_'. $row["data_id"] .'.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';}
    //echo '              <p> <img src="http://www-star.st-and.ac.uk/~jvhs1/ava_plots/lco_latest_'. $row["data_id"] .'.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';}
    else {echo '          <br><p> Data not processed</p>';}
    echo '          </div>';
    echo '      </div>'; // content
    echo '  </div>'; // TABABBLE
    echo '  </div>'; // PHOTO

    echo '  <div id="image" class="tab-pane fade">';
    //echo '    <h3>Menu 2</h3>';
    echo '   <p> <img src="plots/lco_latest_'. $row["data_id"] .'_zoom.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '  </div>'; 
    if ($row["floyds_rdy"] >0){
    echo '  <div id="spec" class="tab-pane fade">';
    //echo '    <h3>Menu 2</h3>';
    echo '   <p> <img src="plots/lco_latest_'. $row["data_id"] .'_spec_avg.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '  </div>'; 
    }
    echo '  <div id="sky" class="tab-pane fade">';
    //echo '    <h3>Menu 1</h3>';
    echo '  <div class="tabbable">';
    echo '      <ul class="nav nav-tabs">';
    if ($row["lco_u"] >0){
    echo '      <li class="active"><a data-toggle="tab" href="#lco_u">u</a></li>';}
    if ($row["lco_g"] >0){
        echo '      <li><a data-toggle="tab" href="#lco_g">g</a></li>';}
    if ($row["lco_r"] >0){
        echo '      <li><a data-toggle="tab" href="#lco_r">r</a></li>';}
    if ($row["lco_i"] >0){
        echo '      <li><a data-toggle="tab" href="#lco_i">i</a></li>';}
    if ($row["lco_z"] >0){
        echo '      <li><a data-toggle="tab" href="#lco_z">z</a></li>';}
    if ($row["lco_B"] >0){
        echo '      <li><a data-toggle="tab" href="#lco_B">B</a></li>';}
    if ($row["lco_V"] >0){
        echo '      <li><a data-toggle="tab" href="#lco_V">V</a></li>';}
    echo '      </ul>';
    echo '      <div class="tab-content">';
    if ($row["lco_u"] >0){
    echo '          <div id="lco_u" class="tab-pane fade in active">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_up_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '          </div>';}
    if ($row["lco_g"] >0){
    echo '          <div id="lco_g" class="tab-pane fade">';
    echo '          <p> <img src="hplots/lco_latest_'. $row["data_id"] .'_gp_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '          </div>';}
    if ($row["lco_r"] >0){
    echo '          <div id="lco_r" class="tab-pane fade">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_rp_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    if ($row["lco_i"] >0){
    echo '          <div id="lco_i" class="tab-pane fade">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_ip_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    if ($row["lco_z"] >0){
    echo '          <div id="lco_z" class="tab-pane fade">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_zs_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    if ($row["lco_B"] >0){
    echo '          <div id="lco_B" class="tab-pane fade">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_B_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    if ($row["lco_V"] >0){
    echo '          <div id="lco_V" class="tab-pane fade">';
    echo '          <p> <img src="plots/lco_latest_'. $row["data_id"] .'_V_sky.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '           </div>';}
    echo '       </div>';
    echo '  </div>';
    echo '  </div>';
    echo '  <div id="stan" class="tab-pane fade">';
    //echo '    <h3>Menu 2</h3>';
    echo '   <p> <img src="plots/lco_latest_'. $row["data_id"] .'_stan.png" style="width:100%;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    echo '  </div>';
    echo '</div>';
    //echo '   <p> <img src="plots/lco_latest_'. $row["data_id"] .'.png" style="width:500px;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';
    //if ($row["hst_0"] >0){
    //echo '            <h4 align="center">Time-resolved spectroscopy</h4><br><p>';
    //echo '       <img src="../assets/ava_spec/F9_spec.png" style="width:400px;" title="Click to enlarge. Open in new tab" alt="Finding chart"> </p>';}
    //echo '     </div>';
    //echo '       <br><div id="chart_od"></div>';
    //echo '<div id="News" class="tabcontent">';
    //echo '<h3>Home</h3>';
    //echo '<p>Home is where the heart is..</p>';
    //echo '</div>';
    //echo '  </a>';
    echo '  </div>';
    echo '  </div>';


    echo '	<div class="panel-group">';
	echo '	  <div class="panel panel-default">';
	echo '	    <div class="panel-heading">';
	echo '	      <h4 class="panel-title">';
	//echo '	        <a data-toggle="collapse" href="#collapse1">Photometry breakdown <i class="far fa-caret-square-down"></i></a></h4>';
     echo '<div class="panel-heading">Photometry breakdown</div>';
	echo '	    </div>';
    //echo '      <div id="collapse1" class="panel-collapse collapse">';
	echo '	    <div id="collapse1" class="panel-body">';
	echo '	      <ul class="list-group">';
    if ($row["lco_cadence"] >0){
	echo '	        <li class="list-group-item">';
	echo '	           	<table class="table table-hover w-auto" style="width:100%"> <tr>';
	echo '				    <th class="column-name-list">LCO</th>';
	echo '				    <td class="column-val"><strong>B</strong></td>';
	echo '				    <td class="column-val"><strong>V</strong></td>';
	echo '				    <td class="column-val"><strong>u</strong></td>';
	echo '				    <td class="column-val"><strong>g</strong></td>';
	echo '				    <td class="column-val"><strong>r</strong></td>';
	echo '				    <td class="column-val"><strong>i</strong></td>';
	echo '				    <td class="column-val"><strong>z</strong></td>';
	echo '				    <td class="column-dates">--</td>';
	echo '				    <td class="column-dates">--</td></tr>';	
	echo '   			<tr>';
	echo '				    <th class="column-name-list">#Epochs</th>';	
	echo '				    <td class="column-val">'. number_format($row["lco_B"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["lco_V"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["lco_u"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["lco_g"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["lco_r"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["lco_i"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["lco_z"], 0, '.', '') .'</td>';
	echo '				    <td class="column-dates">--</td>';
	echo '				    <td class="column-dates">--</td>';
	echo '				</tr> ';
  echo '        <tr>';
  echo '            <th class="column-name-list">Mean Mag (AB)<br>Last 10 days</th>'; 
  echo '            <td class="column-val">'. number_format($row["avg_B"], 2, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["avg_V"], 2, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["avg_u"], 2, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["avg_g"], 2, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["avg_r"], 2, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["avg_i"], 2, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["avg_z"], 2, '.', '') .'</td>';
  echo '            <td class="column-dates">--</td>';
  echo '            <td class="column-dates">--</td>';
  echo '        </tr> ';
  if ($row['merged']==1){
  echo '        <tr>';
  echo '            <th class="column-name-list">Fractional<br>Variability</th>'; 
  echo '            <td class="column-val">'. $row["frac_B"] .'</td>';
  echo '            <td class="column-val">'. $row["frac_V"] .'</td>';
  echo '            <td class="column-val">'. $row["frac_u"] .'</td>';
  echo '            <td class="column-val">'. $row["frac_g"] .'</td>';
  echo '            <td class="column-val">'. $row["frac_r"] .'</td>';
  echo '            <td class="column-val">'. $row["frac_i"] .'</td>';
  echo '            <td class="column-val">'. $row["frac_z"] .'</td>';
  echo '            <td class="column-dates">--</td>';
  echo '            <td class="column-dates">--</td>';
  echo '        </tr> ';}
  echo '</table>';	
  echo '	        </li>';}
    if ($row["lt_cadence"] >0){
  echo '          <li class="list-group-item">';
  echo '              <table class="table table-hover w-auto" style="width:100%;overflow-x:auto;"> <tr>';
  echo '            <th class="column-name-list">LT - Liverpool Telescope</th>';
  echo '            <td class="column-val"><strong></strong></td>';
  echo '            <td class="column-val"><strong></strong></td>';
  echo '            <td class="column-val"><strong>u</strong></td>';
  echo '            <td class="column-val"><strong>g</strong></td>';
  echo '            <td class="column-val"><strong>r</strong></td>';
  echo '            <td class="column-val"><strong>i</strong></td>';
  echo '            <td class="column-val"><strong>z</strong></td>';
  echo '            <td class="column-dates">--</td>';
  echo '            <td class="column-dates">--</td></tr>'; 
  echo '        <tr>';
  echo '            <th class="column-name-list">#Epochs</th>'; 
  echo '            <td class="column-val"></td>';
  echo '            <td class="column-val"></td>';
  echo '            <td class="column-val">'. number_format($row["lt_u"], 0, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["lt_g"], 0, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["lt_r"], 0, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["lt_i"], 0, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["lt_z"], 0, '.', '') .'</td>';
  echo '            <td class="column-dates">--</td>';
  echo '            <td class="column-dates">--</td>';
  echo '        </tr> ';
  echo '              <tr>';
  echo '                  <th class="column-name-list">Mean Mag (AB)<br>Last 10 days</th>'; 
  echo '                  <td class="column-val"></td>';
  echo '                  <td class="column-val"></td>';
  echo '                  <td class="column-val">'. number_format($row["avg_lt_u"], 2, '.', '') .'</td>';
  echo '                  <td class="column-val">'. number_format($row["avg_lt_g"], 2, '.', '') .'</td>';
  echo '                  <td class="column-val">'. number_format($row["avg_lt_r"], 2, '.', '') .'</td>';
  echo '                  <td class="column-val">'. number_format($row["avg_lt_i"], 2, '.', '') .'</td>';
  echo '                  <td class="column-val">'. number_format($row["avg_lt_z"], 2, '.', '') .'</td>';
  echo '                  <td class="column-dates">--</td>';
  echo '                  <td class="column-dates">--</td>';
  echo '              </tr> ';
  echo '</table>';  
  echo '          </li>';}
	if ($row["swift_w2"] >0){
	echo '	        <li class="list-group-item">';
	echo '	           	<table class="table table-hover w-auto" style="width:100%"> <tr>';
	echo '				    <th class="column-name-list">Swift</th>';
    echo '                  <td class="column-val"><strong>X-rays</strong></td>';
    echo '                  <td class="column-val"><strong>UVW2</strong></td>';
	echo '				    <td class="column-val"><strong>UVM2</strong></td>';
	echo '				    <td class="column-val"><strong>UVW1</strong></td>';
	echo '				    <td class="column-val"><strong>U</strong></td>';
	echo '				    <td class="column-val"><strong>B</strong></td>';
	echo '				    <td class="column-val"><strong>V</strong></td>';
	echo '				    <td class="column-dates">--</td>';
	echo '				    <td class="column-dates">--</td></tr>';
    echo '              <tr>';
	echo '				    <th class="column-name-list">#Epochs</th>';	
  echo '            <td class="column-val">'. number_format($row["swift_FX"], 0, '.', '') .'</td>';
  echo '            <td class="column-val">'. number_format($row["swift_w2"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["swift_m2"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["swift_w1"], 0, '.', '') .'</td>';
	echo '				    <td class="column-val">'. number_format($row["swift_U"] , 0, '.', '').'</td>';
	echo '				    <td class="column-val">'. number_format($row["swift_B"] , 0, '.', '').'</td>';
	echo '				    <td class="column-val">'. number_format($row["swift_V"] , 0, '.', '').'</td>';
	echo '				    <td class="column-dates">--</td>';
	echo '				    <td class="column-dates">--</td>';
    echo '              </tr> ';
    echo '              <tr>';
    echo '                  <th class="column-name-list">Mean Mag (AB)<br>Last 10 days</th>'; 
    echo '                  <td class="column-val">'. number_format($row["avg_FX"], 2, '.', '') .'</td>';
    echo '                  <td class="column-val">'. number_format($row["avg_w2"], 2, '.', '') .'</td>';
    echo '                  <td class="column-val">'. number_format($row["avg_m2"], 2, '.', '') .'</td>';
    echo '                  <td class="column-val">'. number_format($row["avg_w1"], 2, '.', '') .'</td>';
    echo '                  <td class="column-val">'. number_format($row["avg_US"], 2, '.', '') .'</td>';
    echo '                  <td class="column-val">'. number_format($row["avg_BS"], 2, '.', '') .'</td>';
    echo '                  <td class="column-val">'. number_format($row["avg_VS"], 2, '.', '') .'</td>';
    echo '                  <td class="column-dates">--</td>';
    echo '                  <td class="column-dates">--</td>';
    echo '              </tr> ';
	echo '			 </table>';	
	echo '	        </li></ul>';}
    if ($row["lco_g"] <-100){
    echo '          <li class="list-group-item">';
    echo '              <table class="table table-hover w-auto" style="width:100%"> <tr>';
    echo '                  <th class="column-name-list">Spectral Lines</th>';
    echo '                  <td class="column-val"><strong>H&alpha;</strong></td>';
    echo '                  <td class="column-val"><strong>H&beta;</strong></td>';
    echo '                  <td class="column-val"><strong>H&gamma;</strong></td>';
    echo '                  <td class="column-val"><strong>HeII</strong></td>';
    echo '                  <td class="column-val"><strong>OIII]</strong></td>';
    echo '                  <td class="column-val"><strong>5100 &#x212B;</strong></td>';
    echo '                  <td class="column-val"><strong>--</strong></td>';
    echo '                  <td class="column-dates">--</td>';
    echo '                  <td class="column-dates">--</td></tr>';
    echo '              <tr>';
    echo '                  <th class="column-name-list">#Epochs</th>'; 
    echo '                  <td class="column-val">'. $row["swift_FX"] .'</td>';
    echo '                  <td class="column-val">'. $row["swift_w2"] .'</td>';
    echo '                  <td class="column-val">'. $row["swift_m2"] .'</td>';
    echo '                  <td class="column-val">'. $row["swift_w1"] .'</td>';
    echo '                  <td class="column-val">'. $row["swift_U"] .'</td>';
    echo '                  <td class="column-val">--</td>';
    echo '                  <td class="column-val">--</td>';
    echo '                  <td class="column-dates">--</td>';
    echo '                  <td class="column-dates">--</td>';
    echo '              </tr> </table>';    
    echo '          </li></ul>';}
	//echo '	        <li class="list-group-item">Three</li>';
	//echo '	      </ul>';
	//echo '	      <div class="panel-footer">Footer</div>';
	echo '	    </div>';
	echo '	  </div>';
    //<!-- close finding charts -->
	    }
	} else {
	    echo "0 results";
	}
	$connection->close();

?>



</div>
<div id="footer">
  <div class="col-md-7" align="left">
    <p class="muted credit"><small>&copy; 2020-2023 Juan V. Hernández Santisteban<br>
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
  </div>
</div> <!-- footer -->
  <!-- jQuery (necessary for Bootstrap's JavaScript plugins) -->
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.11.1/jquery.min.js"></script>
  <!-- Include all compiled plugins (below), or include individual files as needed -->
  <script src="//maxcdn.bootstrapcdn.com/bootstrap/3.2.0/js/bootstrap.min.js"></script>
  <script src="javascripts/create-graph.js"></script>
    <script>
document.getElementById("demo").innerHTML = document.lastModified;
</script>

<script>
$(".hBack").on("click", function(e){
    e.preventDefault();
    window.history.back();
});

function openPage(pageName,elmnt,color) {
  var i, tabcontent, tablinks;
  tabcontent = document.getElementsByClassName("tabcontent");
  for (i = 0; i < tabcontent.length; i++) {
    tabcontent[i].style.display = "none";
  }
  tablinks = document.getElementsByClassName("tablink");
  for (i = 0; i < tablinks.length; i++) {
    tablinks[i].style.backgroundColor = "";
  }
  document.getElementById(pageName).style.display = "block";
  elmnt.style.backgroundColor = color;
}
</script>

</body>
</html>