# Read-only Windows hardware summary for MUH-56. No username, photo paths,
# serial number, MAC address or device ID is printed.
$ErrorActionPreference = 'Stop'
$gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [ordered]@{
        Name = $_.Name
        DriverVersion = $_.DriverVersion
        # WMI AdapterRAM may wrap at 4 GiB on some drivers; do not treat it
        # as a trustworthy VRAM amount when selecting a GPU backend.
        ReportedAdapterRAMGiB = if ($null -ne $_.AdapterRAM) {
            [math]::Round([double]$_.AdapterRAM / 1GB, 2)
        } else { $null }
    }
})
$system = Get-CimInstance Win32_ComputerSystem
[ordered]@{
    RAMGiB = [math]::Round([double]$system.TotalPhysicalMemory / 1GB, 2)
    GPU = $gpu
    Note = 'ReportedAdapterRAMGiB can be inaccurate; no GPU acceleration is enabled by this report.'
} | ConvertTo-Json -Depth 5
