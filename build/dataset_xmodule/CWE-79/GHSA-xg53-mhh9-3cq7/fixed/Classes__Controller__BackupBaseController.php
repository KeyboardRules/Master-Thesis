<?php

namespace NITSAN\NsBackup\Controller;

use RuntimeException;
use TYPO3\CMS\Core\Core\Environment;
use TYPO3\CMS\Core\Utility\GeneralUtility;
use TYPO3\CMS\Extbase\Mvc\Controller\ActionController;
use NITSAN\NsBackup\Domain\Repository\BackupglobalRepository;
use TYPO3\CMS\Extbase\Utility\LocalizationUtility;

/***
 *
 * This file is part of the "Backup" Extension for TYPO3 CMS.
 *
 * For the full copyright and license information, please read the
 * LICENSE.txt file that was distributed with this source code.
 *
 *  (c) 2019
 *
 ***/

/**
 * BackupBaseController
 */
class BackupBaseController extends ActionController
{
    /**
     * phpPath
     *
     * @var string
     */
    public string $phpPath = '';

    /**
     * rootPath
     *
     * @var string
     */
    public string $rootPath = '';

    /**
     * composerRootPath
     *
     * @var string
     */
    public string $composerRootPath = '';

    /**
     * siteUrl
     *
     * @var string
     */
    public string $siteUrl = '';

    /**
     * localStoragePath
     *
     * @var string
     */
    public string $localStoragePath = '';

    /**
     * baseURL
     *
     * @var string
     */
    public string $baseURL = '';

    /**
     * phpbuPath
     *
     * @var string
     */
    public string $phpbuPath = '';

    /**
     * arrDatabase
     *
     * @var array
     */
    public array $arrDatabase = array();

    /**
     * backupFileName
     *
     * @var string
     */
    public string $backupFileName = '';

    /**
     * backupFilePath
     *
     * @var string
     */
    public string $backupFilePath = '';

    /**
     * backupDownloadPath
     *
     * @var string
     */
    public string $backupDownloadPath = '';

    /**
     * backupFile
     *
     * @var string
     */
    public string $backupFile = '';

    /**
     * globalSettingsData
     *
     * @var object
     */
    protected object $globalSettingsData;

    /**
     * prefixFileName
     *
     * @var string
     */
    protected string $prefixFileName;

    /**
     * backupFileMySQL
     */
    protected mixed $backupFileMySQL;


    /**
     * backupDownloadPathMySQL
     */
    protected $backupDownloadPathMySQL;

    public string $exceptionMessage = '';

    /**
     * __construct
     * @param BackupglobalRepository $backupglobalRepository
     */
    public function __construct(
        protected  BackupglobalRepository $backupglobalRepository
    ) {
        $this->exceptionMessage = LocalizationUtility::translate('something.wrong.here', 'ns_backup');

    }

    /**
     * action globalErrorValidation
     *
     * @return string
     */
    public function globalErrorValidation(): string
    {
        // Get global configuration
        $this->globalSettingsData = $this->backupglobalRepository->findAll();

        $arrKeys = ['emails', 'emailSubject', 'compress', 'php', 'root', 'siteurl', 'cleanup', 'cleanupQuantity'];
        $arrValidation = [];
        foreach ($arrKeys as $key) {
            $arrValidation[$key] = LocalizationUtility::translate("global.error.$key", 'ns_backup');
        }

        $errorValidation = implode('', array_map(function ($key, $value) {
            return empty($this->globalSettingsData[0]->$key) ? '<li>' . $value . '</li>' : '';
        }, array_keys($arrValidation), $arrValidation));

        // Let's check configuration for PHPBU
        $arrGetLoadedExtensions = get_loaded_extensions();
        $arrExtensionsToCheck = ['curl', 'dom', 'json'];
        foreach ($arrExtensionsToCheck as $extension) {
            if (!in_array($extension, $arrGetLoadedExtensions)) {
                $errorValidation .= '<li>' . LocalizationUtility::translate("global.error.$extension", 'ns_backup') . '</li>';
            }
        }
        // Check if exec() works
        if (!exec('echo EXEC') == 'EXEC') {
            $errorValidation .= '<li>' . LocalizationUtility::translate('global.error.exec', 'ns_backup') . '</li>';
        }
        return $errorValidation;
    }

    /**
     * action generateBackup
     *
     * @param array $arrPost
     * @return array
     */
    public function generateBackup(array $arrPost): array
    {
        // Get global configuration
        $this->globalSettingsData = $this->backupglobalRepository->findAll();
        // Get PHP Path
        $this->phpPath = !empty($this->globalSettingsData[0]->php)
            ? $this->globalSettingsData[0]->php
            : (exec('which php') ?: 'php ');

        // Get TYPO3 Path
        $this->rootPath = $this->globalSettingsData[0]->root ?? (Environment::getProjectPath() ?? '');

        // Let's change root path to /public in Composer-based installation
        if(Environment::isComposerMode()) {
            $this->rootPath = Environment::getPublicPath();
            $this->composerRootPath = Environment::getComposerRootPath();
            $this->phpbuPath = $this->composerRootPath.'/vendor/nitsan/ns-backup/phpbu.phar';
        }

        // Get Local Storage Path
        $globalBackupStorePath = $this->globalSettingsData[0]->getBackupStorePath();
        $isPublicPath = $this->isPathPublic($globalBackupStorePath);
        if ($globalBackupStorePath == '') {
            $this->localStoragePath = $this->rootPath . '/tx_nsbackup/';
            $jsonFolder = $this->rootPath . '/tx_nsbackup/json/';
        } else {
            $this->localStoragePath = $globalBackupStorePath . '/tx_nsbackup/';
            $jsonFolder = $globalBackupStorePath . '/tx_nsbackup/json/';
        }
        try {
            if (!file_exists($this->localStoragePath)) {
                GeneralUtility::mkdir_deep($this->localStoragePath);
            }
        } catch (RuntimeException $e) {
            return  [
                'log' => 'error',
                'backup_file' => $this->exceptionMessage,
            ];
        }

        // Get Base URL
        $this->siteUrl = '';
        if (!empty($this->globalSettingsData[0]->siteurl)) {
            $this->siteUrl = $this->globalSettingsData[0]->siteurl;
        }
        $path = str_replace($this->rootPath, '', $globalBackupStorePath);
        $this->baseURL = $this->siteUrl . $path . '/tx_nsbackup/';

        // Get PHPHBU Path
        if (Environment::isComposerMode()) {
            $this->phpbuPath = $this->composerRootPath . '/vendor/nitsan/ns-backup/phpbu.phar';
        } else {
            $this->phpbuPath = $this->rootPath . '/typo3conf/ext/ns_backup/phpbu.phar';
        }

        // Get Database Configuration
        $this->arrDatabase = $GLOBALS['TYPO3_CONF_VARS']['DB']['Connections']['Default'];
        $this->arrDatabase['port'] = $this->arrDatabase['port'] ?? '3306';

        // Get Current Date time
        $this->prefixFileName = date('dmY_Hi');

        // Prepare backup filename
        $backupName = $arrPost['backupName'].'_'.$this->prefixFileName;
        $currentDateTime = '';
        $backupNameOriginal = $arrPost['backupName'];
        $backupFileName = strtolower(trim($backupName));
        $backupFileName = preg_replace(['/[\s-]+/', '/[^A-Za-z0-9_]/', '/_+/'], '_', $backupFileName);
        $backupType = $arrPost['backupFolderSettings'];

        // Generates an 8-character random string
        $randomString = substr(md5(uniqid(mt_rand(), true)), 0, 8);
        $backupBaseName = GeneralUtility::trimExplode('_', $backupFileName, true, 3)[1];

        $jsonFile = $backupBaseName . '_' . $randomString . '_' . $backupType . '_configuration.json';
        $logFile = $jsonFolder . $backupBaseName . '_' . $randomString . '_' . $backupType . '_log.json';
        $jsonPath = $jsonFolder . $jsonFile;

        // Prepare backup filename
        $backupFileName = preg_replace(
            '/[^A-Za-z0-9]+/',
            '_',
            preg_replace('/[\s-]+/', '_', strtolower(trim($backupName)))
        );
        // Let's create LOG file if not existis
        if (!file_exists($logFile)) {
            $fh = @fopen($logFile, 'a');
            if($fh != false) {
                @fclose($fh);
            }
        }

        $json = '
            {
                "verbose": true,
                "debug": false,
                "logging": [
                    {
                        "type": "json",
                        "target": "'.$logFile.'"
                    },
                    {
                        "type": "mail",
                        "options": {
                        "transport": "mail",
                        "recipients": "'.$this->globalSettingsData[0]->emails.'",
                        "subject": "[' . $backupType . '] ' . $backupNameOriginal . ' - ' . $this->globalSettingsData[0]->emailSubject . '",
                        "sendOnlyOnError": "'.$this->globalSettingsData[0]->emailNotificationOnError.'"
                        }
                    }
                ],
                "backups": [';

        // Let's check if admin wants "Backup Everyting"
        if ($backupType == 'all') {

            // store date and time before backup
            $currentDateTime = date('Ymd-Hi');
            // Create Database Backup
            $json .= $this->getPhpbuBackup($backupName, 'mysqldump', $backupFileName) . ',';

            // Create Code Backup
            $json .= $this->getPhpbuBackup($backupName, $backupType, $backupFileName);
        } elseif ($backupType == 'other') {
            $json .= $this->getPhpbuBackup($backupName, $backupType, $backupFileName, $arrPost['custompath']);
        } else {
            // Create Specific Selected Type of Backup
            $json .= $this->getPhpbuBackup($backupName, $backupType, $backupFileName);
        }

        $json .= '
                ]
            }
        ';

        try {
            // Ensure the directory exists
            if (!file_exists($jsonFolder)) {
                GeneralUtility::mkdir($jsonFolder);
            }

            // Write JSON content to file
            file_put_contents($jsonPath, $json);

            // Validate and sanitize PHP path
            if (!is_string($this->phpPath) || !file_exists($this->phpPath) || !is_executable($this->phpPath)) {
                throw new RuntimeException("Invalid PHP executable path.");
            }

            // Prepare SSH Command
            $command = $this->phpPath . ' ' . $this->phpbuPath . ' --configuration=' . $jsonPath . ' --verbose';

            // Execute Backup SSH Command
            exec($command, $log, $return_var);
        } catch (RuntimeException $e) {
            return  [
                'log' => 'error',
                'backup_file' => 'Something is wrong here.' . $e->getMessage(),
            ];
        }

        // Validate If SSH command success
        if (count($log) > 0 && is_array($log)) {
            $log = file_get_contents($logFile);

            // Get ready to insert to Backup History
            $arrPost['jsonfile'] = $jsonFile;

            // If Backup Everything, Then let's first-insert MySQL as special case
            if ($backupType == 'all') {
                $arrPost['backup_type'] = 'mysqldump';
                $arrPost['download_url'] = '';
                if ($isPublicPath) {
                    $arrPost['download_url'] = $this->backupDownloadPathMySQL;
                }
                $compressTechnique = $this->globalSettingsData[0]->compress;
                $compressTechniques = [
                    'bzip2' => '.bz2',
                    'zip' => '',
                    'gzip' => '.gz',
                    'xz' => '.xz',
                ];

                $compressTechnique = $compressTechniques[$compressTechnique] ?? '.bz2';

                $path = str_replace("/all", "", $this->backupFilePath);
                $backupFileMySQL = $path . '/mysqldump' . '/mysqldump' . '-' . $currentDateTime . '.sql' . $compressTechnique;
                $fileSize = $this->convertFilesize(filesize($backupFileMySQL));
                $arrPost['size'] = $fileSize;

                $arrPost['filenames'] = $backupFileMySQL;
                $this->backupglobalRepository->addBackupData($arrPost);

            }

            // Insert to Database > Backup History
            $arrPost['download_url'] = '';
            if ($isPublicPath) {
                $arrPost['download_url'] = $this->backupDownloadPath;
            }
            $arrPost['log'] = $log;

            try {
                $fileSize = $this->convertFilesize(filesize($this->backupFile));
            } catch (\Exception $e) {
                return  [
                    'log' => 'error',
                    'backup_file' => 'Something is wrong here. Please check you Global Settings',
                ];
            }

            $arrPost['size'] = $fileSize;
            $arrPost['filenames'] = $this->backupFile;

            $downloadURL = '';
            if ($isPublicPath) {
                $downloadURL = $this->backupDownloadPath;
            }
            $this->backupglobalRepository->addBackupData($arrPost);
            $arrReturn = [
                'log' => $log,
                'backup_file' => $this->backupFile,
                'download_url' => $downloadURL,
            ];
        } else {
            $arrReturn = [
                'log' => 'error',
                'backup_file' => $this->backupFile,
            ];
        }
        return $arrReturn;
    }

    /**
     * Generate PHP BU action getPhpbuBackupJSON
     * @param string $backupName
     * @param string $backupType
     * @param string $backupFileName
     * @param string|null $rawName
     * @return string
     */
    protected function getPhpbuBackup(string $backupName, string $backupType, string $backupFileName, ?string $rawName = null): string
    {
        $json = $ignoreUploads = '';
        $json .= '
            {
                "name": "' . $backupName . '",';

        $backupExtFile = '.tar';
        switch ($backupType) {
            case 'mysqldump':
                $json .= '
                "source": {
                    "type": "mysqldump",
                    "options": {
                        "host": "' . $this->arrDatabase['host'] . '",
                        "port": "' . $this->arrDatabase['port'] . '",
                        "databases": "' . $this->arrDatabase['dbname'] . '",
                        "user": "' . $this->arrDatabase['user'] . '",
                        "password": "' . $this->arrDatabase['password'] . '"
                    }
                },';
                $backupExtFile = '.sql';
                break;

            default:
                $targetPath = ($backupType == 'all') ? '' : $backupType;

                // Exclude uploads/tx_nsbackup
                if ($backupType == 'uploads') {
                    $ignoreUploads = ',"exclude": "tx_nsbackup"';
                }
                if ($backupType == 'all') {
                    $ignoreUploads = ',"exclude": "uploads/tx_nsbackup,typo3temp"';
                }

                $sourcePath = $this->rootPath . '/' . $targetPath;

                // In composer-mode, let's figure out vendor folder
                if (($backupType == 'vendor') && ($this->composerRootPath !== null && strlen($this->composerRootPath) > 0)) {
                    $sourcePath = $this->composerRootPath . '/' . $targetPath;
                }

                if ($backupType == 'other') {
                    $json .= '
                    "source": {
                        "type": "tar",
                        "options": {
                            "path": "' . $rawName . '"' . $ignoreUploads . '
                        }
                    },';
                } else {
                    $json .= '
                    "source": {
                        "type": "tar",
                        "options": {
                            "path": "' . $sourcePath . '"' . $ignoreUploads . '
                        }
                    },';
                }
        }

        // PATCH If compress=bzip2
        $compressTechnique = $this->globalSettingsData[0]->compress;
        $compressTechniques = [
            'bzip2' => '.bz2',
            'zip' => '',
            'gzip' => '.gz',
            'xz' => '.xz',
        ];

        $compressTechnique = $compressTechniques[$compressTechnique] ?? '.bz2';
        //echo $compressTechnique;exit;

        $this->backupFilePath = $this->localStoragePath . $backupType;

        // Physical file
        $this->backupFile = $this->backupFilePath . '/' . md5($backupType).'-'.date('Ymd-Hi') . $backupExtFile . $compressTechnique;

        // Download file
        $this->backupDownloadPath =
            $this->baseURL .
            $backupType . '/' .
            md5($backupType) . '-' . date('Ymd-Hi') . $backupExtFile . $compressTechnique;

        // If Backup Type = ALL then, Let's consider mysql as special-case
        if ($backupType == 'mysqldump') {
            if ($this->globalSettingsData[0]->compress == 'zip') {
                $compressTechnique = '';
            }
            $this->backupFileMySQL = $this->backupFilePath . '/' . md5($backupType) . '-' . date('Ymd-Hi') . $backupExtFile . $compressTechnique;
            $this->backupDownloadPathMySQL =
                $this->baseURL . $this->backupFileMySQL =
                    $backupType . '/' . md5($backupType) . '-' . date('Ymd-Hi') . $backupExtFile . $compressTechnique;
        }
        $this->backupFileName = md5($backupType) . '-%Y%m%d-%H%i' . $backupExtFile;
        $json .= '
                "target": {
                    "dirname": "' . $this->backupFilePath . '",
                    "filename": "' . $this->backupFileName . '",
                    "compress": "' . $this->globalSettingsData[0]->compress . '"
                },';

        $json .= '
                "cleanup": {
                    "type": "' . $this->globalSettingsData[0]->cleanup . '",
                    "options": {
                        "amount": "' . $this->globalSettingsData[0]->cleanupQuantity . '"
                    }
                }
            }
        ';
        return $json;
    }


    /**
     * Convert File Size
     * @param mixed $bytes
     * @return string
     */
    protected function convertFilesize(mixed $bytes): string
    {
        if ($bytes >= 1073741824) {
            $bytes = number_format($bytes / 1073741824, 2) . ' GB';
        } elseif ($bytes >= 1048576) {
            $bytes = number_format($bytes / 1048576, 2) . ' MB';
        } elseif ($bytes >= 1024) {
            $bytes = number_format($bytes / 1024, 2) . ' KB';
        } elseif ($bytes > 1) {
            $bytes = $bytes . ' bytes';
        } elseif ($bytes == 1) {
            $bytes = $bytes . ' byte';
        } else {
            $bytes = '0 bytes';
        }
        return $bytes;
    }

    /**
     * @param string $path
     * @return boolean
     */
    public function isPathPublic(string $path): bool
    {
        if (!Environment::isComposerMode()) {
            $valuesToCheck = ['typo3', 'typo3conf', 'vendor', 'typo3temp', 'bin'];
            $parts = array_filter(explode('/', rtrim($path, '/')));
            return empty(array_intersect($parts, $valuesToCheck));
        }
        return str_contains(rtrim($path, '/'), Environment::getPublicPath());
    }
}
