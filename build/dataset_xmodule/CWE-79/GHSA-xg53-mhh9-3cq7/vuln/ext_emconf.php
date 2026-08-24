<?php

$EM_CONF['ns_backup'] = [
    'title' => 'Backup Plus',
    'description' => 'Easily backup your entire TYPO3 website. The Backup Plus extension for TYPO3 lets you save your code, files, and database with just a few clicks. Install Backup Plus and connect it to your cloud storage (like Google Drive, Dropbox, Amazon S3, SFTP, Rsync, etc.) and backup your entire TYPO3 site manually with a single click.

    *** Live Demo: https://demo.t3planet.com/t3-extensions/backup *** Premium Version, Documentation & Free Support: https://t3planet.com/typo3-backup-extension',
    'category' => 'module',
    'author' => 'T3: Rohan Parmar, T3: Divya Goklani, T3: Nilesh Malankiya, QA: Gautam Kunjadiya',
    'author_email' => 'sanjay@nitsan.in',
    'author_company' => 'T3Planet // NITSAN',
    'state' => 'stable',
    'uploadfolder' => 1,
    'createDirs' => '',
    'version' => '13.0.0',
    'constraints' => [
        'depends' => [
            'typo3' => '12.0.0-13.9.99',
        ],
        'conflicts' => [],
        'suggests' => [],
    ],
    'autoload' => [
        'classmap' => ['Classes/']
    ]
];
