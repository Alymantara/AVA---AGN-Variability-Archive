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


    /* Swift tracker page */

    .swift-intro {
        margin-bottom: 25px;
        line-height: 1.7;
    }

    .swift-tabs {
        margin-top: 20px;
        margin-bottom: 0;
    }
/*
    .swift-plot-container {
        padding: 20px 0;
    }*/

/*    .swift-plot-container iframe {
        display: block;
        width: 100%;
        height: 750px;
        border: 1px solid #ddd;
        background: #fff;
    }*/

    .swift-plot-container {
    padding: 20px 0;
    text-align: center;
}

    .swift-plot {
        display: block;
        width: 100%;
        max-width: 800px;
        height: auto;
        margin: 0 auto;
    }

    @media (max-width: 767px) {
        .swift-plot-container iframe {
            height: 550px;
        }
    }

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

    <h3>Swift Orbit Tracker</h3>

    <div class="swift-intro">

        <p>
            This page tracks Swift's orbital evolution and decay as it gradually
            approaches its inevitable re-entry into Earth's atmosphere.
        </p>

        <p>
            Swift's orbit is tracked using orbital elements derived from
            observations available through the
            <a href="https://heasarc.gsfc.nasa.gov/"
               target="_blank"
               rel="noopener noreferrer">
                <strong>HEASARC archive</strong>
            </a>.
            These elements are used to follow the orbital evolution and estimate
            its decay over time. The resulting predictions are crude
            extrapolations and should be treated as first-order estimates only.
        </p>

    </div>


    <!-- PLOT TABS -->

    <ul class="nav nav-tabs swift-tabs" role="tablist">

        <li class="active">
            <a href="#swift-decay"
               role="tab"
               data-toggle="tab">
                Swift Orbital Decay
            </a>
        </li>

        <li>
            <a href="#swift-analysis"
               role="tab"
               data-toggle="tab">
                Orbital decay with Solar Activity
            </a>
        </li>

    </ul>


    <!-- TAB CONTENT -->

    <div class="tab-content">

        <!-- FIRST TAB: DISPLAYED BY DEFAULT -->

        <div class="tab-pane fade in active"
             id="swift-decay">

            <div class="swift-plot-container">

                <img
                    src="plots/swift_decay.png"
                    title="Swift orbital decay plot" 
                    class="swift-plot"
                >

                <p class="text-muted">
                    <small>
                        <a href="plots/swift_decay.png"
                           target="_blank"
                           rel="noopener noreferrer">
                            Open Swift orbital decay plot in a new tab
                        </a>
                    </small>
                </p>

            </div>

        </div>


        <!-- SECOND TAB -->

        <div class="tab-pane fade"
             id="swift-analysis">

            <div class="swift-plot-container">

                <img
                    src="plots/new_plot_swift.png"
                    title="Additional Swift orbital analysis"
                    class="swift-plot">

                <p class="text-muted">
                    <small>
                        <a href="plots/new_plot_swift.png"
                           target="_blank"
                           rel="noopener noreferrer">
                            Open additional plot in a new tab
                        </a>
                    </small>
                </p>

            </div>

        </div>

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
