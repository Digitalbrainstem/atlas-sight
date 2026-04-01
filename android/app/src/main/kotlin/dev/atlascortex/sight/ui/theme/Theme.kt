package dev.atlascortex.sight.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

/** Always dark — high contrast color scheme for visual accessibility. */
private val SightColorScheme = darkColorScheme(
    primary = FrostCyan,
    onPrimary = DarkSlate,
    secondary = AuroraPurple,
    onSecondary = PureWhite,
    background = DarkSlate,
    onBackground = PureWhite,
    surface = DarkSurface,
    onSurface = PureWhite,
    error = DangerRed,
    onError = PureWhite,
)

/** Large text typography — minimum 18sp for accessibility. */
private val SightTypography = Typography(
    displayLarge = TextStyle(fontSize = 36.sp, fontWeight = FontWeight.Bold, color = PureWhite),
    headlineLarge = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, color = PureWhite),
    headlineMedium = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.SemiBold, color = PureWhite),
    titleLarge = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.SemiBold, color = PureWhite),
    bodyLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.Normal, color = LightGray),
    bodyMedium = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Normal, color = LightGray),
    labelLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.Bold, color = FrostCyan),
)

@Composable
fun AtlasSightTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = DarkSlate.toArgb()
            window.navigationBarColor = DarkSlate.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = SightColorScheme,
        typography = SightTypography,
        content = content,
    )
}
