<?php

return [
    'ctrl' => [
        'title' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal',
        'label' => 'emails',
        'tstamp' => 'tstamp',
        'crdate' => 'crdate',
        'sortby' => 'sorting',
        'versioningWS' => true,
        'languageField' => 'sys_language_uid',
        'transOrigDiffSourceField' => 'l10n_diffsource',
        'delete' => 'deleted',
        'hideTable' => true,
        'enablecolumns' => [
            'disabled' => 'hidden',
            'starttime' => 'starttime',
            'endtime' => 'endtime',
        ],
        'searchFields' => 'emails,email_from,email_notification_on_error,cleanup_server_name,cleanup_server_value,cleanup,compress,php,root,siteurl',
        'iconfile' => 'EXT:ns_backup/Resources/Public/Icons/tx_nsbackup_domain_model_backupglobal.gif',
        'security' => [
            'ignorePageTypeRestriction' => true,
        ],
    ],
    'types' => [
        '1' => ['showitem' => 'sys_language_uid, l10n_diffsource, hidden, emails, email_notification_on_error, cleanup_server_name, cleanup_server_value, cleanup, compress,php,root,siteurl, --div--;LLL:EXT:frontend/Resources/Private/Language/locallang_ttc.xlf:tabs.access, starttime, endtime'],
    ],
    'columns' => [
        'sys_language_uid' => [
            'exclude' => true,
            'label' => 'LLL:EXT:core/Resources/Private/Language/locallang_general.xlf:LGL.language',
            'config' => [
                'type' => 'language',
            ],
        ],
        'l10n_diffsource' => [
            'config' => [
                'type' => 'passthrough',
            ],
        ],
        't3ver_label' => [
            'label' => 'LLL:EXT:lang/locallang_general.xlf:LGL.versionLabel',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'max' => 255,
            ],
        ],
        'hidden' => [
            'exclude' => true,
            'label' => 'LLL:EXT:lang/locallang_general.xlf:LGL.hidden',
            'config' => [
                'type' => 'check'
            ],
        ],
        'starttime' => [
            'exclude' => true,
            'behaviour' => [
                'allowLanguageSynchronization' => true
            ],
            'label' => 'LLL:EXT:lang/locallang_general.xlf:LGL.starttime',
            'config' => [
                'type' => 'input',
                'renderType' => 'datetime',
                'size' => 13,
                'eval' => 'datetime',
                'default' => 0,
            ],
        ],
        'endtime' => [
            'exclude' => true,
            'behaviour' => [
                'allowLanguageSynchronization' => true
            ],
            'label' => 'LLL:EXT:lang/locallang_general.xlf:LGL.endtime',
            'config' => [
                'type' => 'input',
                'renderType' => 'datetime',
                'size' => 13,
                'eval' => 'datetime',
                'default' => 0,
                'range' => [
                    'upper' => mktime(0, 0, 0, 1, 1, 2038)
                ],
            ],
        ],

        'emails' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.emails',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'email_subject' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.email_subject',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'email_from' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.email_subject',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'email_notification_on_error' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.email_notification_on_error',
            'config' => [
                'type' => 'input',
                'size' => 4,
                'eval' => 'number'
            ]
        ],
        'cleanup' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.cleanup',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'cleanup_quantity' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.cleanupquantity',
            'config' => [
                'type' => 'input',
                'size' => 4,
                'eval' => 'number'
            ],
        ],
        'compress' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.compress',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'php' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.php',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'root' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.root',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'siteurl' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.siteurl',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
        'backup_store_path' => [
            'exclude' => true,
            'label' => 'LLL:EXT:ns_backup/Resources/Private/Language/locallang_db.xlf:tx_nsbackup_domain_model_backupglobal.backup_store_path',
            'config' => [
                'type' => 'input',
                'size' => 30,
                'eval' => 'trim'
            ],
        ],
    ],
];
