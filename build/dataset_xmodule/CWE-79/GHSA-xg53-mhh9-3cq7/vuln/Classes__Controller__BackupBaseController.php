<?php

namespace NITSAN\NsBackup\Controller;

use RuntimeException;
use TYPO3\CMS\Core\Core\Environment;
use TYPO3\CMS\Core\Exception;
use TYPO3\CMS\Core\Utility\GeneralUtility;
use TYPO3\CMS\Extbase\Mvc\Controller\ActionController;
use NITSAN\NsBackup\Domain\Repository\BackupglobalRepository;
use TYPO3\CMS\Extbase\Utility\LocalizationUtility as transalte;

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
        $this->exceptionMessage = transalte::translate('something.wrong.here', 'ns_backup');

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
            $arrValidation[$key] = transalte::translate("global.error.$key", 'ns_backup');
        }

        $errorValidation = implode('', array_map(function ($key, $value) {
            return empty($this->globalSettingsData[0]->$key) ? '<li>' . $value . '</li>' : '';
        }, array_keys($arrValidation), $arrValidation));

        // Let's check configuration for PHPBU
        $arrGetLoadedExtensions = get_loaded_extensions();
        $arrExtensionsToCheck = ['curl', 'dom', 'json'];
        foreach ($arrExtensionsToCheck as $extension) {
            if (!in_array($extension, $arrGetLoadedExtensions)) {
                $errorValidation .= '<li>' . transalte::translate("global.error.$extension", 'ns_backup') . '</li>';
            }
        }
        // Check if exec() works
        if (!exec('echo EXEC') == 'EXEC') {
            $errorValidation .= '<li>' . transalte::translate('global.error.exec', 'ns_backup') . '</li>';
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
        $this->phpbuPath = $this->rootPath.'/typo3conf/ext/ns_backup/phpbu.phar';

        // Let's change root path to /public in Composer-based installation
        if(Environment::isComposerMode()) {
            $this->rootPath = Environment::getPublicPath();
            $this->composerRootPath = Environment::getComposerRootPath();
            $this->phpbuPath = $this->composerRootPath.'/vendor/nitsan/ns-backup/phpbu.phar';
        }

        // Get Local Storage Path
        $this->localStoragePath = $this->rootPath.'/uploads/tx_nsbackup/';
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
        $this->siteUrl = $this->globalSettingsData[0]->siteurl ?? '';
        $this->baseURL = $this->siteUrl . '/uploads/tx_nsbackup/';

        // Get Database Configuration
        $this->arrDatabase = $GLOBALS['TYPO3_CONF_VARS']['DB']['Connections']['Default'];
        $this->arrDatabase['port'] = $this->arrDatabase['port'] ?? '3306';

        // Get Current Date time
        $this->prefixFileName = date('dmY_Hi');

        $backupNameOriginal = $arrPost['backupName'];
        $backupName = $this->prefixFileName.'_'.$arrPost['backupName'];
        $backupType = $arrPost['backupFolderSettings'];

        // Prepare backup filename
        $backupFileName = preg_replace(
            '/[^A-Za-z0-9]+/',
            '_',
            preg_replace('/[\s-]+/', '_', strtolower(trim($backupName)))
        );

        $jsonFolder = $this->rootPath.'/uploads/tx_nsbackup/json/';
        $jsonFile = GeneralUtility::trimExplode('_', $backupFileName, true, 3)[2] . '_' . $backupType . '_configuration.json';
        $logFile = $jsonFolder . GeneralUtility::trimExplode('_', $backupFileName, true, 3)[2] . '_' . $backupType . '_log.json';
        $jsonPath = $jsonFolder.$jsonFile;

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
                        "subject": "['.$backupType.'] '.$backupNameOriginal. ' - '.$this->globalSettingsData[0]->emailSubject.'",
                        "sendOnlyOnError": "'.$this->globalSettingsData[0]->emailNotificationOnError.'"
                        }
                    }
                ],
                "backups": [';

        // Let's check if admin wants "Backup Everyting"
        if ($backupType == 'all') {
            // Create Database Backup
            $json .= $this->getPhpbuBackup($backupName, 'mysqldump', $backupFileName). ',';

            // Create Code Backup
            $json .= $this->getPhpbuBackup($backupName, $backupType, $backupFileName);
        } else {
            // Create Specific Selected Type of Backup
            $json .= $this->getPhpbuBackup($backupName, $backupType, $backupFileName);
        }

        $json .= '
                ]
            }
        ';

        try {
            // Let's create JSCON folder does not exists
            if (!file_exists($jsonFolder)) {
                GeneralUtility::mkdir_deep($jsonFolder);
            }

            // Let's create JSON file
            file_put_contents($jsonPath, $json);

            // Prepare SSH Command
            $command = $this->phpPath. ' '. $this->phpbuPath.' --configuration='.$jsonPath.' --verbose';

            // Execute Backup SSH Command
            exec($command, $log);
        } catch (RuntimeException $e) {
            return  [
                'log' => 'error',
                'backup_file' => $this->exceptionMessage,
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
                $arrPost['download_url'] = $this->backupDownloadPathMySQL;
                $fileSize = $this->convertFilesize(filesize($this->backupFileMySQL));
                $arrPost['size'] = $fileSize;
                $arrPost['filenames'] = $this->backupFileMySQL;
                $this->backupglobalRepository->addBackupData($arrPost);
            }

            // Insert to Database > Backup History
            $arrPost['download_url'] = $this->backupDownloadPath;
            $arrPost['log'] = $log;
            try {
                $fileSize = $this->convertFilesize(filesize($this->backupFile));
            } catch (Exception $e) {
                return  [
                    'log' => 'error',
                    'backup_file' => $this->exceptionMessage,
                ];
            }

            $arrPost['size'] = $fileSize;
            $arrPost['filenames'] = $this->backupFile;

            $this->backupglobalRepository->addBackupData($arrPost);

            $arrReturn = [
                'log' => $log,
                'backup_file' => $this->backupFile,
                'download_url' => $this->backupDownloadPath,
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
     * @return string
     */
    protected function getPhpbuBackup(string $backupName, string $backupType, string $backupFileName): string
    {
        $json = '';
        $json .= '
            {
                "name": "'.$backupName.'",';

        $backupExtFile = '.tar';
        if ($backupType == 'mysqldump') {
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
        } else {
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
            if ($backupType == 'vendor' && $this->composerRootPath && strlen($this->composerRootPath) > 0) {
                $sourcePath = $this->composerRootPath . '/' . $targetPath;
            }

            $ignoreUploads = $ignoreUploads ?? '';
            $json .= '
                "source": {
                    "type": "tar",
                    "options": {
                        "path": "' . $sourcePath . '"' . $ignoreUploads . '
                    }
                },';
        }

        // PATCH If compress=bzip2
        $compressTechnique = $this->globalSettingsData[0]->compress;
        switch ($compressTechnique) {
            case 'bzip2':
            case '':
                $compressTechnique = '.bz2';
                break;
            case 'zip':
                $compressTechnique = '';
                break;
            case 'gzip':
                $compressTechnique = '.gz';
                break;
            case 'xz':
                $compressTechnique = '.xz';
                break;
            default:
                break;
        }

        $this->backupFilePath = $this->localStoragePath.$backupType;
        $this->backupFileName = $backupFileName.$backupExtFile;
        // Physical file
        $this->backupFile = $this->backupFilePath . '/' . $backupType.'-'.date('Ymd-Hi') . $backupExtFile . $compressTechnique;

        // Download file
        $this->backupDownloadPath =
            $this->baseURL .
            $backupType . '/' .
            $backupType.'-'.date('Ymd-Hi') . $backupExtFile . $compressTechnique;

        // If Backup Type = ALL then, Let's consider mysql as special-case
        if ($backupType == 'mysqldump') {
            $compressTechnique = $this->globalSettingsData[0]->compress == 'zip' ? '' : $compressTechnique;
            $fileName = 'mysqldump' . '-' . date('Ymd-Hi') . $backupExtFile . $compressTechnique;
            $this->backupFileMySQL = $this->backupFilePath . '/' . $fileName;
            $this->backupDownloadPathMySQL = $this->baseURL . $backupType . '/' . $fileName;
        }

        $this->backupFileName =  $backupType.'-%Y%m%d-%H%i' . $backupExtFile;

        $json .= '
                "target": {
                    "dirname": "'.$this->backupFilePath.'",
                    "filename": "'.$this->backupFileName.'",
                    "compress": "'.$this->globalSettingsData[0]->compress.'"
                },';

        $json .= '
                "cleanup": {
                    "type": "'.$this->globalSettingsData[0]->cleanup.'",
                    "options": {
                        "amount": '.$this->globalSettingsData[0]->cleanupQuantity.'
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
}
