<?php
// Initialize the session
session_start();

$projects = [

    '2020B' => [
        '2020B',
        '2021A',
        '2021B',
        '2022A',
        '2022B',
        '2023A'
    ],

    '2023B' => [
        '2023B',
        '2024A',
        '2024B',
        '2025A',
        '2025B',
        '2026A'
    ],

    '2026B' => [
        '2026B'
    ]

];

$default_project = '2026B';

?>

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>AVA - AGN Variability Archive</title>

<link rel="icon"
      type="image/x-icon"
      href="favicon2.ico">

<!-- Bootstrap -->
<link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.2.0/css/bootstrap.min.css"
      rel="stylesheet">

<link href="../assets/css/style_ava.css"
      rel="stylesheet">

<!-- Aladin Lite -->
<link rel="stylesheet"
      href="https://aladin.u-strasbg.fr/AladinLite/api/v2/latest/aladin.min.css">

<!-- Font Awesome -->
<link rel="stylesheet"
      href="https://use.fontawesome.com/releases/v5.13.0/css/all.css">

<link rel="stylesheet"
      href="https://use.fontawesome.com/releases/v5.13.0/css/v4-shims.css">

<!-- jQuery -->
<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.11.1/jquery.min.js"></script>

<!-- Sortable tables -->
<script src="sorttable.js"></script>


<!-- HTML5 Shim and Respond.js IE8 support -->
<!--[if lt IE 9]>
  <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
  <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
<![endif]-->


<script type="text/javascript">

    var nW, nH, oH, oW;

    function zoomToggle(
        iWideSmall,
        iHighSmall,
        iWideLarge,
        iHighLarge,
        whichImage
    ) {

        oW = whichImage.style.width;
        oH = whichImage.style.height;

        if ((oW == iWideLarge) || (oH == iHighLarge)) {

            nW = iWideSmall;
            nH = iHighSmall;

        } else {

            nW = iWideLarge;
            nH = iHighLarge;

        }

        whichImage.style.width = nW;
        whichImage.style.height = nH;
    }

</script>


<style>

    .project-tabs {
        margin-bottom: 20px;
    }

    .semester-tabs {
        margin-top: 15px;
        margin-bottom: 20px;
    }

    .plot-container {
        text-align: center;
        margin-top: 20px;
        margin-bottom: 30px;
    }

    .plot-container img {
        width: 100%;
        max-width: 1400px;
        height: auto;
    }

    .nav-tabs > li > a,
    .nav-pills > li > a {
        font-weight: 600;
    }

</style>

</head>

<body>

<!-- ========================================================= -->

<!-- HEADER -->

<!-- ========================================================= -->

<div class="container">

<h1>
    <a href="http://www.alymantara.com/ava/index.php"
       style="color:black; text-decoration:none">

        AVA
        <small>AGN Variability Archive</small>

        <img src="../assets/images/banner.png"
             height="50"
             alt="AGN Variability Archive">

    </a>
</h1>


<!-- ===================================================== -->
<!-- NAVIGATION BAR -->
<!-- ===================================================== -->

<div class="navbar navbar-default" role="navigation">

    <div class="navbar-header">

        <button type="button"
                class="navbar-toggle"
                data-toggle="collapse"
                data-target=".navbar-collapse">

            <span class="sr-only">Toggle navigation</span>

            <span class="icon-bar"></span>
            <span class="icon-bar"></span>
            <span class="icon-bar"></span>

        </button>

    </div>


    <div class="collapse navbar-collapse">

        <ul class="nav navbar-nav">

            <li>
                <a href="index.php" title="Homepage">
                    <i class="fas fa-home"></i>
                    AVA Archive
                </a>
            </li>

            <li>
                <a href="ava_about.php" title="About">
                    About
                </a>
            </li>

            <li>
                <a href="ava_data.php" title="Data Format">
                    Data Format
                </a>
            </li>

            <li>
                <a href="ava_live.php" title="Live Updates">
                    Live Updates
                </a>
            </li>

            <li>
                <a href="ava_publications.php" title="Publications">
                    Publications
                </a>
            </li>

            <li>
                <a href="ava_team.php" title="About">
                    Team
                </a>
            </li>

      <li>
          <a href="swift_tracker.php" title="About">
              Swift Orbit
          </a>
      </li>
        </ul>


        <!-- ================================================= -->
        <!-- LOGIN -->
        <!-- ================================================= -->

        <ul class="nav navbar-nav navbar-right">

            <?php if (isset($_SESSION['username'])): ?>

                <li>
                    <a class="btn btn-outline-primary"
                       href="index.php"
                       role="button"
                       style="color:black">

                        Welcome
                        <?php echo htmlspecialchars($_SESSION['username']); ?>

                        <i class="fas fa-sign-in"></i>

                    </a>
                </li>


                <li>
                    <a class="btn btn-outline-primary"
                       href="logout.php"
                       role="button"
                       style="color:red">

                        Logout
                        <i class="fas fa-sign-out-alt"></i>

                    </a>
                </li>


            <?php else: ?>

                <li>
                    <a class="btn btn-outline-primary"
                       href="login.php"
                       role="button"
                       style="color:red">

                        Login
                        <i class="fas fa-sign-in-alt"></i>

                    </a>
                </li>

            <?php endif; ?>

        </ul>

    </div>

</div>

</div>

<!-- ========================================================= -->

<!-- MAIN CONTENT -->

<!-- ========================================================= -->

<div class="container">

<h3>
    Live updates
</h3>


<p>

    The following plots show the usage of the allocated
    1m &amp; 2m time per semester
    (dotted black line, total time/Days in semester)
    against the used time for 1m (green),
    2m-FLOYDS (red) and 2m-MuSCAT3 (purple).

    These numbers are taken from the LCO API service
    and are updated every 6 hours.

    <br><br>

    For daily allocation information, check:

    <a href="https://schedule.lco.global/"
       target="_blank"
       rel="noopener noreferrer">

        <strong>LCO daily schedule</strong>

    </a>

</p>


<!-- ===================================================== -->
<!-- PROJECT TABS -->
<!-- ===================================================== -->

<h3>
    Semester Usage
</h3>


<ul class="nav nav-tabs nav-justified project-tabs">

    <?php foreach ($projects as $project => $semesters): ?>

        <li
            <?php if ($project == $default_project): ?>
                class="active"
            <?php endif; ?>
        >

            <a data-toggle="tab"
               href="#project_<?php echo htmlspecialchars($project); ?>">

                <?php echo htmlspecialchars($project); ?>

            </a>

        </li>

    <?php endforeach; ?>

</ul>


<!-- ===================================================== -->
<!-- PROJECT CONTENT -->
<!-- ===================================================== -->

<div class="tab-content">


    <?php foreach ($projects as $project => $semesters): ?>

        <?php
            $latest_semester = $semesters[count($semesters) - 1];
        ?>


        <div id="project_<?php echo htmlspecialchars($project); ?>"
             class="tab-pane fade
             <?php if ($project == $default_project): ?>
                 in active
             <?php endif; ?>">


            <!-- ================================================= -->
            <!-- SEMESTER TABS -->
            <!-- ================================================= -->

            <ul class="nav nav-pills nav-justified semester-tabs">

                <?php foreach ($semesters as $semester): ?>

                    <li
                        <?php if ($semester == $latest_semester): ?>
                            class="active"
                        <?php endif; ?>
                    >

                        <a data-toggle="tab"
                           href="#plot_<?php echo htmlspecialchars($semester); ?>">

                            <?php echo htmlspecialchars($semester); ?>

                        </a>

                    </li>

                <?php endforeach; ?>

            </ul>


            <!-- ================================================= -->
            <!-- SEMESTER PLOT CONTENT -->
            <!-- ================================================= -->

            <div class="tab-content">


                <?php foreach ($semesters as $semester): ?>

                    <div id="plot_<?php echo htmlspecialchars($semester); ?>"
                         class="tab-pane fade
                         <?php if ($semester == $latest_semester): ?>
                             in active
                         <?php endif; ?>">


                        <div class="plot-container">

                            <img src="plots/lco_usage_<?php echo htmlspecialchars($semester); ?>.png"
                                 alt="LCO usage for <?php echo htmlspecialchars($semester); ?>"
                                 class="img-responsive center-block" style="height:500px;width:auto;">


                        </div>

                    </div>


                <?php endforeach; ?>


            </div>


        </div>


    <?php endforeach; ?>


</div>

</div>

<!-- ========================================================= -->

<!-- FOOTER -->

<!-- ========================================================= -->

<div class="container">

<div id="footer">

    <div class="col-md-7"
         align="left">

        <p class="muted credit">

            <small>

                &copy; 2020-2026 Juan V. Hernández Santisteban

                <br>

                Last Updated:
                <span id="demo"></span>

            </small>

        </p>

    </div>


    <div class="col-md-1"
         align="right">

        <a rel="license"
           href="https://creativecommons.org/licenses/by-sa/4.0/">

            <img alt="Creative Commons Licence"
                 style="border-width:0"
                 src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png">

        </a>

    </div>


    <div class="col-md-4"
         align="right">

        <p class="muted credit">

            <small>

                This work is licensed under a

                <a rel="license"
                   href="https://creativecommons.org/licenses/by-sa/4.0/">

                    Creative Commons Attribution-ShareAlike
                    4.0 International License

                </a>.

            </small>

        </p>

    </div>


</div>

</div>

<!-- ========================================================= -->

<!-- BOOTSTRAP JAVASCRIPT -->

<!-- ========================================================= -->

<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.2.0/js/bootstrap.min.js"></script>

<script>

    document.getElementById("demo").innerHTML =
        document.lastModified;

</script>

</body>
</html>
