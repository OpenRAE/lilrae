# Compose a participant workbench

Use trusted entry assembly with an enrolled, unexpired guest binding.
The [workbench reference](participant-workbench.md) defines authority, browser routes, MCP capture, and required checks.

## Assemble the application

1. Get the enrolled `GuestDispatchBinding` through the existing guest-management owner.
2. Configure project and state paths through `LocalWorkbenchSettings`.
3. Select the fixed installed LilRAE executable.
4. Pass a trusted browser-session verifier that returns `BrowserPrincipal`.
5. Match the caller and single role with the enrolled grant.
6. Pass the existing trusted TLS context for guest HTTPS services.
7. Call `create_local_workbench_app` with these trusted inputs.
8. For appliance delivery, use `create_appliance_workbench_app` with the required binding and signed boundary evidence.
9. Let the outer launcher establish sessions, allocate listeners, and configure DNS and TLS termination.
10. Examine required capture and runtime identity before participant access.

Do not mount the operator API in the participant application.
Do not accept participant-supplied executable paths, commands, credentials, Docker endpoints, or service destinations.

## Publish the participant desktop

1. Select the installed participant-desktop provider for the admitted pack.
2. Set `LILRAE_PARTICIPANT_DESKTOP_ACCOUNT` to the existing participant account in trusted launch assembly.
3. Start the admitted scenario through the supported lifecycle.
4. Examine the private desktop files and resolved console URLs after readiness.
5. Make sure that stop, reset, or failed startup withdraws the old surface.

The [desktop reference](../reference/participant-profile.md#participant-desktop) owns file names, permissions, and content restrictions.
