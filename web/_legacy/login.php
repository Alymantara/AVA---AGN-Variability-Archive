<?php
// Initialize the session
session_start();
 
// Check if the user is already logged in, if yes then redirect him to welcome page
if(isset($_SESSION["loggedin"]) && $_SESSION["loggedin"] === true){
    header("location: index.php");
    exit;
}
 
// Include config file
//require_once "config.php";
require_once('./includes/dbconnect.php');

 
// Define variables and initialize with empty values
$username = $password = "";
$username_err = $password_err = $login_err = "";
 
// Processing form data when form is submitted
if($_SERVER["REQUEST_METHOD"] == "POST"){
 
    // Check if username is empty
    if(empty(trim($_POST["username"]))){
        $username_err = "Please enter username.";
    } else{
        $username = trim($_POST["username"]);
    }
    
    // Check if password is empty
    if(empty(trim($_POST["password"]))){
        $password_err = "Please enter your password.";
    } else{
        $password = trim($_POST["password"]);
    }
    
    // Validate credentials
    if(empty($username_err) && empty($password_err)){
        // Prepare a select statement
        $sql = "SELECT id, username, password FROM users WHERE username = ?";
        
        if($stmt = mysqli_prepare($link, $sql)){
            // Bind variables to the prepared statement as parameters
            mysqli_stmt_bind_param($stmt, "s", $param_username);
            
            // Set parameters
            $param_username = $username;
            
            // Attempt to execute the prepared statement
            if(mysqli_stmt_execute($stmt)){
                // Store result
                mysqli_stmt_store_result($stmt);
                
                // Check if username exists, if yes then verify password
                if(mysqli_stmt_num_rows($stmt) == 1){                    
                    // Bind result variables
                    mysqli_stmt_bind_result($stmt, $id, $username, $hashed_password);
                    if(mysqli_stmt_fetch($stmt)){
                        if(password_verify($password, $hashed_password)){
                            // Password is correct, so start a new session
                            session_start();
                            
                            // Store data in session variables
                            $_SESSION["loggedin"] = true;
                            $_SESSION["id"] = $id;
                            $_SESSION["username"] = $username;                            
                            
                            // Redirect user to welcome page
                            header("location: index.php");
                        } else{
                            // Password is not valid, display a generic error message
                            $login_err = "Invalid username or password.";
                        }
                    }
                } else{
                    // Username doesn't exist, display a generic error message
                    $login_err = "Invalid username or password.";
                }
            } else{
                echo "Oops! Something went wrong. Please try again later.";
            }

            // Close statement
            mysqli_stmt_close($stmt);
        }
    }
    
    // Close connection
    mysqli_close($link);
}
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

<div class="container">
<?php

if( $_GET['status'] == 'success'):
  echo '<h4><font color="#eb4d4b">Your application has now been sent for approval!<br> Check your email for further instructions.</font></h4>';
endif;

if( $_GET['status'] == 'deleted'):
  echo '<h4><font color="#eb4d4b">Record was succesfully deleted!</font></h4>';
endif;
?>
    <div class="col-md-4">
        <h2>Login</h2>
        <p>Please fill in your credentials to login.</p>

        <?php 
        if(!empty($login_err)){
            echo '<div class="alert alert-danger">' . $login_err . '</div>';
        }        
        ?>

        <form action="<?php echo htmlspecialchars($_SERVER["PHP_SELF"]); ?>" method="post">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" class="form-control <?php echo (!empty($username_err)) ? 'is-invalid' : ''; ?>" value="<?php echo $username; ?>">
                <span class="invalid-feedback"><?php echo $username_err; ?></span>
            </div>    
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" class="form-control <?php echo (!empty($password_err)) ? 'is-invalid' : ''; ?>">
                <span class="invalid-feedback"><?php echo $password_err; ?></span>
            </div>
            <div class="form-group">
                <input type="submit" class="btn btn-primary" value="Login">
            </div>
            <p>Don't have an account? <a href="signup.php">Sign up now</a>.</p>
        </form>
    </div>    
</div> <!-- footer -->

<div class="container">
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
