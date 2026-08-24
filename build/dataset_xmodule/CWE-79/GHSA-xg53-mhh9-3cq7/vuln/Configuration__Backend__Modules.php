<?php

$backupController = \NITSAN\NsBackup\Controller\BackupsController::class;
$backupglobalController = \NITSAN\NsBackup\Controller\BackupglobalController::class;

return [
    'nitsan_nsbackup' => [
        'parent' => 'tools',
        'position' => ['before' => 'top'],
        'access' => 'user',
        'path' => '/module/nitsan/NsBackupBackup    ',
        'icon' => 'EXT:ns_backup/Resources/Public/Icons/module-nsbackup.svg',
        'labels' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_backup.xlf',
        'extensionName' => 'NsBackup',
        'controllerActions' => [
            $backupController => 'dashboard, backuprestore, deletebackupbackup, globalsetting, manualbackup',
            $backupglobalController => 'globalsetting, create, update',
        ],
    ],
];
