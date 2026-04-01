package dev.atlascortex.sight.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import dev.atlascortex.sight.core.SightMode
import dev.atlascortex.sight.ui.theme.*

/**
 * Minimal Compose UI — status text + large send button.
 * All elements have TalkBack content descriptions.
 * Designed for eyes-free use: large touch targets, high contrast.
 */
@Composable
fun SightScreen(
    statusText: String,
    currentMode: SightMode,
    isReady: Boolean,
    isDownloading: Boolean,
    downloadProgress: Float,
    onActivate: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkSlate)
            .padding(24.dp)
            .semantics { contentDescription = "Atlas Sight main screen" },
        verticalArrangement = Arrangement.SpaceBetween,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Top: Mode indicator
        Text(
            text = "${currentMode.label} Mode",
            style = MaterialTheme.typography.headlineLarge,
            color = FrostCyan,
            modifier = Modifier
                .padding(top = 32.dp)
                .semantics { contentDescription = "${currentMode.label} mode active" },
        )

        // Center: Status text (large, high contrast)
        Column(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = statusText,
                style = MaterialTheme.typography.headlineMedium,
                color = PureWhite,
                textAlign = TextAlign.Center,
                modifier = Modifier.semantics {
                    contentDescription = statusText
                },
            )

            if (isDownloading) {
                Spacer(modifier = Modifier.height(24.dp))
                LinearProgressIndicator(
                    progress = { downloadProgress },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(8.dp)
                        .semantics {
                            contentDescription = "Download progress: ${(downloadProgress * 100).toInt()} percent"
                        },
                    color = FrostCyan,
                    trackColor = DarkSurface,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "${(downloadProgress * 100).toInt()}%",
                    style = MaterialTheme.typography.bodyLarge,
                    color = FrostCyan,
                )
            }
        }

        // Bottom: Large activation button
        Button(
            onClick = onActivate,
            modifier = Modifier
                .size(200.dp)
                .padding(bottom = 48.dp)
                .semantics {
                    contentDescription = "Activate Atlas. Large button. Double-tap to describe what's in front of you."
                },
            shape = CircleShape,
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isReady) FrostCyan else MediumGray,
                contentColor = DarkSlate,
            ),
            enabled = isReady,
        ) {
            Text(
                text = if (isReady) "ATLAS" else "LOADING",
                style = MaterialTheme.typography.headlineLarge,
                color = DarkSlate,
            )
        }
    }
}
