const { chromium } = require('playwright');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU';
const CHAT = '-1003179573402';
const URL = 'https://1xlite-7636770.bar/ru/live/baccarat';
const LAST_NUMBER_FILE = './last_number.txt';

const bot = new TelegramBot(TOKEN, { polling: false });

let lastMessageId = null;
let lastMessageText = '';
let lastGameNumber = '0';

if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

function formatCards(cards) {
    return cards.join('');
}

function determineWinner(playerScore, bankerScore) {
    if (playerScore > bankerScore) return 'П1';
    if (bankerScore > playerScore) return 'П2';
    return 'X';
}

function getCardCountColor(playerCount, bankerCount) {
    return `#C${playerCount}_${bankerCount}`;
}

function isNaturalWin(score, cardCount) {
    return cardCount === 2 && (score >= 7 && score <= 9);
}

function getNaturalFlag(playerScore, playerCount, bankerScore, bankerCount) {
    if (playerCount === 2 && bankerCount === 2) {
        if ((playerScore >= 7 && playerScore <= 9) || (bankerScore >= 7 && bankerScore <= 9)) {
            return ' #R🔵';
        }
    }
    return '';
}

async function sendOrEditTelegram(newMessage) {
    if (!newMessage || newMessage === lastMessageText) return;
    try {
        if (lastMessageId) {
            await bot.editMessageText(newMessage, {
                chat_id: CHAT,
                message_id: lastMessageId
            });
        } else {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
        }
        lastMessageText = newMessage;
    } catch (e) {
        console.log('TG error:', e.message);
    }
}

async function findFirstLiveGame(page) {
    const games = await page.$$('.dashboard-game');
    for (const game of games) {
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        if (!hasTimer) continue;

        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) return await link.getAttribute('href');
        }
    }
    return null;
}

async function getCards(page) {
    const playerBlock = await page.$('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__cards');
    const player = playerBlock ? await playerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const bankerBlock = await page.$('.baccarat-player--is-reversed .baccarat-player__cards');
    const banker = bankerBlock ? await bankerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }) : [];

    const pScore = await page.$eval('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__number', el => el.textContent).catch(() => '0');
    const bScore = await page.$eval('.baccarat-player--is-reversed .baccarat-player__number', el => el.textContent).catch(() => '0');

    return { player, banker, pScore, bScore };
}

async function monitorGame(page, gameNumber, startTime) {
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };
    let gameOverCount = 0;
    let lastHitMessage = '';
    let lastPlayerCardCount = 0;
    let lastBankerCardCount = 0;

    while (true) {
        // Проверяем, не прошло ли 2 минуты
        const elapsedSeconds = (Date.now() - startTime) / 1000;
        if (elapsedSeconds >= 120) {
            console.log(`⏱ Прошло 2 минуты, закрываю браузер`);
            return true;
        }

        const cards = await getCards(page);

        // Проверка на завершение игры через селектор
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            if (!panel) return false;
            
            const style = window.getComputedStyle(panel);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                return false;
            }
            
            const caption = panel.querySelector('.ui-caption');
            return caption && caption.textContent.includes('Игра завершена');
        });

        if (isGameOver) {
            gameOverCount++;
            console.log(`⚠️ Обнаружен game-over панель (попытка ${gameOverCount}/3)`);
            
            if (gameOverCount >= 3) {
                console.log(`🏁 Игра #${gameNumber} завершена, жду 10 секунд...`);
                await page.waitForTimeout(10000);
                
                const finalCheck = await page.evaluate(() => {
                    const panel = document.querySelector('.market-grid__game-over-panel');
                    if (!panel) return false;
                    const style = window.getComputedStyle(panel);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                        return false;
                    }
                    const caption = panel.querySelector('.ui-caption');
                    return caption && caption.textContent.includes('Игра завершена');
                });
                
                if (finalCheck) {
                    console.log(`✅ Подтверждено`);
                    return true;
                } else {
                    console.log(`⚠️ Панель исчезла`);
                    gameOverCount = 0;
                    continue;
                }
            }
            await page.waitForTimeout(1000);
            continue;
        } else {
            gameOverCount = 0;
        }

        // Проверка на завершение через dashboard-game-info__period
        const isFinished = await page.evaluate(() => {
            const el = document.querySelector('.dashboard-game-info__period');
            return el && el.textContent.includes('Игра завершена');
        });

        if (isFinished) {
            const total = parseInt(cards.pScore) + parseInt(cards.bScore);
            const winner = determineWinner(parseInt(cards.pScore), parseInt(cards.bScore));
            const cardCountColor = getCardCountColor(cards.player.length, cards.banker.length);
            const naturalFlag = getNaturalFlag(
                parseInt(cards.pScore), cards.player.length,
                parseInt(cards.bScore), cards.banker.length
            );
            
            let message;
            if (winner === 'П1') {
                message = `#N${gameNumber} ✅${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})${naturalFlag} #${winner} #T${total} ${cardCountColor}`;
            } else if (winner === 'П2') {
                message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ✅${cards.bScore} (${formatCards(cards.banker)})${naturalFlag} #${winner} #T${total} ${cardCountColor}`;
            } else {
                message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) 🔰 ${cards.bScore} (${formatCards(cards.banker)})${naturalFlag} #${winner} #T${total} ${cardCountColor}`;
            }

            await sendOrEditTelegram(message);
            console.log(`✅ Игра #${gameNumber} завершена`);
            return true;
        }

        if (cards.player.length > 0 && cards.banker.length > 0) {
            let message;
            const playerScore = parseInt(cards.pScore);
            const bankerScore = parseInt(cards.bScore);
            
            const playerNatural = isNaturalWin(playerScore, cards.player.length);
            const bankerNatural = isNaturalWin(bankerScore, cards.banker.length);
            
            if (playerNatural || bankerNatural) {
                message = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
            } else {
                // Проверяем, добрал ли игрок новую карту
                if (cards.player.length > lastPlayerCardCount) {
                    const hitMsg = `⏱№${gameNumber} 👉${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
                    if (hitMsg !== lastHitMessage) {
                        message = hitMsg;
                        console.log(`🃏 Игрок добрал карту: ${cards.player[cards.player.length-1]}`);
                        lastHitMessage = hitMsg;
                    }
                }
                // Проверяем, добрал ли банкир новую карту
                else if (cards.banker.length > lastBankerCardCount) {
                    const hitMsg = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
                    if (hitMsg !== lastHitMessage) {
                        message = hitMsg;
                        console.log(`🃏 Банкир добрал карту: ${cards.banker[cards.banker.length-1]}`);
                        lastHitMessage = hitMsg;
                    }
                }
                // Обычное состояние без добора
                else {
                    message = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
                }
            }

            const cardsChanged = 
                JSON.stringify(cards.player) !== JSON.stringify(lastCards.player) ||
                JSON.stringify(cards.banker) !== JSON.stringify(lastCards.banker) ||
                cards.pScore !== lastCards.pScore ||
                cards.bScore !== lastCards.bScore;

            if (cardsChanged && message) {
                await sendOrEditTelegram(message);
                lastCards = { ...cards };
            }
        }

        lastPlayerCardCount = cards.player.length;
        lastBankerCardCount = cards.banker.length;

        await page.waitForTimeout(2000);
    }
}

async function run() {
    const startTime = Date.now();
    console.log(`\n🆕 Новый браузер открыт в ${new Date().toLocaleTimeString()}`);
    
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    try {
        await page.goto(URL);
        console.log('🔍 Ищу первый стол с таймером...');

        let liveLink = null;
        while (!liveLink) {
            liveLink = await findFirstLiveGame(page);
            if (!liveLink) {
                await page.waitForTimeout(1000);
            }
        }

        console.log('🎯 Захожу в стол:', liveLink);
        await page.click(`a[href="${liveLink}"]`);
        await page.waitForTimeout(3000);

        let gameNumber = await page.evaluate(() => {
            const infoEl = document.querySelector('.dashboard-game-info__additional-info');
            if (infoEl && infoEl.textContent.trim()) {
                return infoEl.textContent.trim();
            }
            
            const timeEl = document.querySelector('.dashboard-game-info__time, .dashboard-game-info__period');
            if (timeEl && timeEl.textContent.trim()) {
                const match = timeEl.textContent.trim().match(/\d+$/);
                if (match) return match[0];
            }
            
            return null;
        });

        if (!gameNumber) {
            gameNumber = (parseInt(lastGameNumber) + 1).toString();
            console.log('⚠️ Номер не найден, присваиваю:', gameNumber);
        } else {
            console.log('🎰 Номер стола:', gameNumber);
        }

        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);

        let attempts = 0;
        let cards = { player: [], banker: [] };
        while (attempts < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
            await page.waitForTimeout(5000);
            cards = await getCards(page);
            attempts++;
        }

        if (cards.player.length > 0 && cards.banker.length > 0) {
            const finished = await monitorGame(page, gameNumber, startTime);
            if (finished) {
                console.log('🏁 Завершаем сессию');
            }
        }
    } catch (error) {
        console.log('Ошибка:', error.message);
    } finally {
        await browser.close();
        console.log(`🔴 Браузер закрыт в ${new Date().toLocaleTimeString()}`);
        lastMessageId = null;
        lastMessageText = '';
    }
}

// Бесконечный цикл с интервалом 45 секунд
(async () => {
    console.log('🤖 Бот запущен. Последний номер:', lastGameNumber);
    console.log('⏱ Интервал: открытие каждые 45 секунд, работа 2 минуты\n');
    
    while (true) {
        await run();
        
        // Ждем 45 секунд перед следующим открытием
        console.log(`⏱ Жду 45 секунд до следующего браузера...\n`);
        await new Promise(resolve => setTimeout(resolve, 45000));
    }
})();
