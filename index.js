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
let browserCounter = 0;

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
    
    for (let attempt = 1; attempt <= 3; attempt++) {
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
            return;
        } catch (e) {
            console.log(`❌ TG error (попытка ${attempt}/3):`, e.message);
            
            if (attempt === 3) {
                try {
                    const msg = await bot.sendMessage(CHAT, newMessage);
                    lastMessageId = msg.message_id;
                    lastMessageText = newMessage;
                    console.log('✅ Отправлено новое сообщение');
                } catch (sendError) {
                    console.log('❌ Критическая ошибка TG:', sendError.message);
                }
            } else {
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }
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

async function monitorGame(page, gameNumber, browserId) {
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };
    let gameOverCount = 0;
    let lastHitMessage = '';
    let lastPlayerCardCount = 0;
    let lastBankerCardCount = 0;

    while (true) {
        const cards = await getCards(page);

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
            console.log(`[Браузер ${browserId}] ⚠️ Game-over панель (${gameOverCount}/3)`);
            
            if (gameOverCount >= 3) {
                console.log(`[Браузер ${browserId}] 🏁 Игра #${gameNumber} завершена, жду 10 сек...`);
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
                    console.log(`[Браузер ${browserId}] ✅ Подтверждено`);
                    return true;
                } else {
                    console.log(`[Браузер ${browserId}] ⚠️ Панель исчезла`);
                    gameOverCount = 0;
                    continue;
                }
            }
            await page.waitForTimeout(1000);
            continue;
        } else {
            gameOverCount = 0;
        }

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
            console.log(`[Браузер ${browserId}] ✅ Игра #${gameNumber} завершена`);
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
                if (cards.player.length > lastPlayerCardCount) {
                    const hitMsg = `⏱№${gameNumber} 👉${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)})`;
                    if (hitMsg !== lastHitMessage) {
                        message = hitMsg;
                        console.log(`[Браузер ${browserId}] 🃏 Игрок добрал: ${cards.player[cards.player.length-1]}`);
                        lastHitMessage = hitMsg;
                    }
                }
                else if (cards.banker.length > lastBankerCardCount) {
                    const hitMsg = `⏱№${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
                    if (hitMsg !== lastHitMessage) {
                        message = hitMsg;
                        console.log(`[Браузер ${browserId}] 🃏 Банкир добрал: ${cards.banker[cards.banker.length-1]}`);
                        lastHitMessage = hitMsg;
                    }
                }
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

async function runBrowser() {
    const browserId = ++browserCounter;
    const startTime = Date.now();
    const closeTime = new Date(startTime + 120000); // +2 минуты
    
    console.log(`\n🟢 [Браузер ${browserId}] открылся в ${new Date(startTime).toLocaleTimeString()}`);
    console.log(`   [Браузер ${browserId}] закроется в ${closeTime.toLocaleTimeString()}`);
    
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    // Принудительное закрытие через 2 минуты
    const forceCloseTimeout = setTimeout(async () => {
        console.log(`⏱ [Браузер ${browserId}] 2 минуты истекли, закрываю`);
        await browser.close().catch(() => {});
    }, 120000);

    try {
        await page.goto(URL);
        
        // Поиск стола (максимум 30 сек)
        let liveLink = null;
        const searchStart = Date.now();
        
        while (!liveLink && (Date.now() - searchStart) < 30000) {
            liveLink = await findFirstLiveGame(page);
            if (!liveLink) {
                await page.waitForTimeout(1000);
            }
        }
        
        if (!liveLink) {
            console.log(`⚠️ [Браузер ${browserId}] не нашел стол за 30 сек`);
            return;
        }

        console.log(`🎯 [Браузер ${browserId}] заходит в стол:`, liveLink);
        await page.click(`a[href="${liveLink}"]`);
        await page.waitForTimeout(3000);

        // Получаем номер игры
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
            console.log(`⚠️ [Браузер ${browserId}] номер не найден, присваиваю:`, gameNumber);
        } else {
            console.log(`🎰 [Браузер ${browserId}] номер стола:`, gameNumber);
        }

        // Сохраняем номер глобально
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);

        // Ждем появления карт
        let attempts = 0;
        let cards = { player: [], banker: [] };
        while (attempts < 12 && (cards.player.length === 0 || cards.banker.length === 0)) {
            await page.waitForTimeout(5000);
            cards = await getCards(page);
            attempts++;
        }

        if (cards.player.length > 0 && cards.banker.length > 0) {
            await monitorGame(page, gameNumber, browserId);
        }
        
    } catch (error) {
        console.log(`❌ [Браузер ${browserId}] ошибка:`, error.message);
    } finally {
        clearTimeout(forceCloseTimeout);
        await browser.close();
        console.log(`🔴 [Браузер ${browserId}] закрылся в ${new Date().toLocaleTimeString()}\n`);
    }
}

// ЗАПУСК: Каждые 45 секунд новый браузер
(async () => {
    console.log('🤖 Бот запущен');
    console.log('⏱ Каждые 45 секунд - новый браузер');
    console.log('⏱ Каждый браузер живет 2 минуты\n');
    
    while (true) {
        runBrowser(); // Запускаем не дожидаясь завершения
        await new Promise(resolve => setTimeout(resolve, 45000)); // Ждем 45 сек
    }
})();
