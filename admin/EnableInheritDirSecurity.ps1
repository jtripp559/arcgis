# Specify the path to the directory where you want to enable inheritance
$directoryPath = "C:\Program Files\ArcGIS\Server\framework\runtime\ArcGIS\bin\Python\envs"

# Get all items within the directory, including subfolders and files
$items = Get-ChildItem -Path $directoryPath -Recurse -Force

# Prepare variables for progress tracking
$totalItems = $items.Count
$currentItemNumber = 0

# Display initial progress
Write-Progress -Activity "Enabling inheritance" -Status "Starting..." -PercentComplete 0

# Iterate through each item
foreach ($item in $items) {
    # Update progress
    $currentItemNumber++
    $progressPercent = ($currentItemNumber / $totalItems) * 100
    Write-Progress -Activity "Enabling inheritance" -Status "Processing item: $($item.FullName)" -PercentComplete $progressPercent

    # Get the current ACL
    $acl = Get-Acl -Path $item.FullName

    # Check if inheritance is already enabled
    if ($acl.AreAccessRulesProtected) {
        # Inheritance is disabled, so enable it
        $acl.SetAccessRuleProtection($false, $true) # Parameters: isProtected, preserveInheritance
        # Apply the modified ACL back to the item
        Set-Acl -Path $item.FullName -AclObject $acl
        Write-Host "Enabled inheritance for: $($item.FullName)"
    }
}

# Additionally, ensure the top-level directory itself has inheritance enabled
$acl = Get-Acl -Path $directoryPath
if ($acl.AreAccessRulesProtected) {
    # $acl.SetAccessRuleProtection($false, $true) # Enable inheritance
    # Set-Acl -Path $directoryPath -AclObject $acl
    Write-Host "Enabled inheritance for: $directoryPath"
}

# Finalize progress
Write-Progress -Activity "Enabling inheritance" -Status "Completed" -Completed
Write-Host "Inheritance enabled for all items."
